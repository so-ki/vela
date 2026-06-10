"""Corpus maintenance agent — Reg Feed scan, LexML sync, impact alerts (Claude for Legal pattern)."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.scenario import InvestigationScenario
from app.services.legal_corpus_service import rebuild_corpus_index
from app.services.legal_ingest import load_corpus
from app.services.legal_monitor import (
    _load_state,
    _save_state,
    compute_corpus_diff,
    scan_regulatory_updates,
)
from app.services.lexml_fetch_service import enrich_corpus_document_from_lexml
from app.services.reg_feed_service import scan_reg_feed

AGENT_INTERVAL_HOURS = 6
MAX_LEXML_SYNC_PER_RUN = 12
PENDING_REVIEW_PATH = Path(__file__).resolve().parents[1] / "data" / "corpus_pending_review.json"


def _load_pending_review() -> list[dict[str, Any]]:
    if not PENDING_REVIEW_PATH.exists():
        return []
    with open(PENDING_REVIEW_PATH, encoding="utf-8") as f:
        data = json.load(f)
    return list(data) if isinstance(data, list) else []


def _save_pending_review(items: list[dict[str, Any]]) -> None:
    PENDING_REVIEW_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(PENDING_REVIEW_PATH, "w", encoding="utf-8") as f:
        json.dump(items[:200], f, ensure_ascii=False, indent=2)
        f.write("\n")


def enqueue_pending_corpus_review(entries: list[dict[str, Any]]) -> int:
    """Append reg-feed / diff hints to human review queue — never auto-merge corpus."""
    if not entries:
        return 0
    existing = _load_pending_review()
    seen = {(e.get("source_id"), e.get("url"), e.get("title")) for e in existing}
    added = 0
    for entry in entries:
        key = (entry.get("source_id"), entry.get("url"), entry.get("title"))
        if key in seen:
            continue
        existing.insert(
            0,
            {
                **entry,
                "status": "pending_review",
                "queued_at": _utcnow_iso(),
            },
        )
        seen.add(key)
        added += 1
    _save_pending_review(existing)
    return added


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _collect_checklist_codes(payload: dict[str, Any] | None) -> set[str]:
    codes: set[str] = set()
    if not payload:
        return codes
    for section in payload.get("sections") or payload.get("sections_with_legal") or []:
        for item in section.get("items") or []:
            code = item.get("code")
            if code:
                codes.add(code)
    return codes


def _collect_corpus_ids_from_payload(payload: dict[str, Any] | None) -> set[str]:
    ids: set[str] = set()
    if not payload:
        return ids
    for section in payload.get("sections_with_legal") or []:
        for item in section.get("items") or []:
            for hit in item.get("legal_hits") or []:
                doc_id = hit.get("id") or hit.get("doc_id")
                if doc_id:
                    ids.add(str(doc_id))
    return ids


def _impact_analysis(
    db: Session,
    *,
    changed_docs: list[dict[str, Any]],
    affected_codes: set[str],
) -> list[dict[str, Any]]:
    """Map corpus/law changes to projects, contracts, diligence artifacts."""
    changed_ids = {str(d.get("id")) for d in changed_docs if d.get("id")}
    impacts: list[dict[str, Any]] = []

    scenarios = (
        db.query(InvestigationScenario)
        .filter(InvestigationScenario.legal_deleted_at.is_(None))
        .order_by(InvestigationScenario.updated_at.desc())
        .limit(80)
        .all()
    )

    for scenario in scenarios:
        payload = (scenario.checklist.payload if scenario.checklist else None) or {}
        if not payload.get("brief") and not payload.get("sections_with_legal"):
            continue

        scenario_codes = _collect_checklist_codes(payload)
        scenario_corpus_ids = _collect_corpus_ids_from_payload(payload)
        code_overlap = sorted(scenario_codes & affected_codes)
        corpus_overlap = sorted(scenario_corpus_ids & changed_ids)

        if not code_overlap and not corpus_overlap:
            continue

        artifacts: list[dict[str, Any]] = [
            {
                "type": "investigation",
                "label": "协查包 / 双语简报",
                "path": f"/scenarios/{scenario.id}/review",
                "affected_checklist_codes": code_overlap,
                "affected_corpus_ids": corpus_overlap,
            }
        ]

        hub = payload.get("project_hub") or {}
        modules = hub.get("modules") or {}

        for doc in modules.get("contracts", {}).get("documents") or []:
            if doc.get("status") != "analyzed":
                continue
            findings = doc.get("findings") or []
            red_count = sum(1 for f in findings if f.get("risk") == "RED")
            if code_overlap or red_count:
                artifacts.append(
                    {
                        "type": "contract",
                        "label": doc.get("filename") or doc.get("id") or "合同",
                        "path": f"/projects/{scenario.id}?tab=contracts",
                        "risk_summary": f"RED {red_count} 条" if red_count else "已分析",
                        "affected_checklist_codes": code_overlap,
                    }
                )

        for doc in modules.get("diligence", {}).get("documents") or []:
            if doc.get("status") != "analyzed":
                continue
            artifacts.append(
                {
                    "type": "diligence",
                    "label": doc.get("filename") or doc.get("id") or "尽调文件",
                    "path": f"/projects/{scenario.id}?tab=diligence",
                    "affected_checklist_codes": code_overlap,
                }
            )

        archived = (payload.get("document_extract") or {}).get("archived_files") or []
        material_files = [f.get("filename") for f in archived if f.get("filename")]

        impacts.append(
            {
                "scenario_id": scenario.id,
                "project_name": scenario.project_name,
                "progress_status": scenario.status,
                "affected_checklist_codes": code_overlap,
                "affected_corpus_ids": corpus_overlap,
                "artifacts": artifacts,
                "material_files": material_files[:8],
                "suggested_actions": _suggested_actions(code_overlap, corpus_overlap, artifacts),
            }
        )

    return impacts


def _suggested_actions(
    codes: list[str],
    corpus_ids: list[str],
    artifacts: list[dict[str, Any]],
) -> list[str]:
    actions: list[str] = []
    if codes:
        actions.append(f"对核查项 {', '.join(codes[:5])} 发起增量协查或重跑 RAG")
    if corpus_ids:
        actions.append("复核已绑定法条摘录是否与最新官方文本一致")
    if any(a.get("type") == "contract" for a in artifacts):
        actions.append("重新运行合同审查，核对责任/LGPD/管辖等条款")
    if any(a.get("type") == "diligence" for a in artifacts):
        actions.append("更新尽调结论并与协查清单交叉核对")
    if not actions:
        actions.append("在法源维护页确认语料变更并通知业务是否需要重跑协查")
    return actions


def _batch_lexml_sync(*, limit: int = MAX_LEXML_SYNC_PER_RUN) -> list[dict[str, Any]]:
    corpus = load_corpus()
    results: list[dict[str, Any]] = []
    synced = 0
    for doc in corpus.get("sources", []):
        if synced >= limit:
            break
        if doc.get("source") not in ("lexml", "stf", "stj") or not (doc.get("urn") or "").strip():
            continue
        prev_len = len(doc.get("text_pt") or "")
        outcome = enrich_corpus_document_from_lexml(str(doc["id"]), persist=True)
        if outcome.get("status") == "ok":
            synced += 1
            new_len = int(outcome.get("new_length") or 0)
            if abs(new_len - prev_len) > 30:
                results.append(
                    {
                        "doc_id": doc["id"],
                        "title_pt": doc.get("title_pt"),
                        "change_type": "lexml_sync",
                        "previous_length": prev_len,
                        "new_length": new_len,
                        "checklist_codes": list(doc.get("checklist_codes") or []),
                    }
                )
    return results


def run_corpus_maintenance_agent(
    db: Optional[Session] = None,
    *,
    scheduled: bool = False,
    sync_lexml: bool = True,
    auto_reindex: bool = True,
) -> dict[str, Any]:
    """Scan feeds, sync LexML-backed corpus, notify legal of impacted projects."""
    run_id = f"agent-{uuid.uuid4().hex[:10]}"
    started = _utcnow_iso()
    state = _load_state()
    prev_snapshot = dict(state.get("doc_snapshot") or {})

    feed = scan_reg_feed()
    pending_entries: list[dict[str, Any]] = []
    for item in feed.get("feed_items") or []:
        if item.get("level") in ("high", "medium") or not item.get("reachable", True):
            pending_entries.append(
                {
                    "source_id": item.get("source_id"),
                    "title": item.get("title"),
                    "url": item.get("url"),
                    "summary": item.get("summary"),
                    "affected_checklist_codes": item.get("affected_checklist_codes") or [],
                    "reason": "reg_feed_scan",
                }
            )
    for doc in (feed.get("policy_diff") or {}).get("changed_documents") or []:
        pending_entries.append(
            {
                "source_id": "local-corpus",
                "title": doc.get("title_pt") or doc.get("id"),
                "url": doc.get("url"),
                "doc_id": doc.get("id"),
                "checklist_codes": doc.get("checklist_codes") or [],
                "reason": "corpus_diff",
            }
        )
    queued = enqueue_pending_corpus_review(pending_entries)

    lexml_updates: list[dict[str, Any]] = []
    if sync_lexml:
        lexml_updates = _batch_lexml_sync()

    diff = compute_corpus_diff(prev_snapshot=prev_snapshot if prev_snapshot else None)
    for item in lexml_updates:
        if not any(d.get("id") == item.get("doc_id") for d in diff.get("changed_documents") or []):
            diff.setdefault("changed_documents", []).append(item)
            diff.setdefault("affected_checklist_codes", []).extend(item.get("checklist_codes") or [])
            diff["has_changes"] = True
    diff["affected_checklist_codes"] = sorted(set(diff.get("affected_checklist_codes") or []))

    reindex_result: dict[str, Any] | None = None
    if auto_reindex and (lexml_updates or diff.get("has_changes")):
        reindex_result = rebuild_corpus_index(force=True)

    scan_regulatory_updates(force_reindex=False)

    affected_codes = set(diff.get("affected_checklist_codes") or [])
    for doc in diff.get("changed_documents") or []:
        affected_codes.update(doc.get("checklist_codes") or [])

    impacts: list[dict[str, Any]] = []
    if db is not None and affected_codes:
        impacts = _impact_analysis(
            db,
            changed_docs=list(diff.get("changed_documents") or []),
            affected_codes=affected_codes,
        )

    notifications: list[dict[str, Any]] = list(state.get("agent_notifications") or [])
    new_notifications: list[dict[str, Any]] = []

    if lexml_updates or diff.get("has_changes") or impacts:
        summary_parts: list[str] = []
        if lexml_updates:
            summary_parts.append(f"已从 LexML 同步 {len(lexml_updates)} 条语料")
        if diff.get("changed_documents"):
            summary_parts.append(f"语料变更 {len(diff.get('changed_documents') or [])} 条")
        if impacts:
            summary_parts.append(f"影响 {len(impacts)} 个项目")

        notif = {
            "id": f"notif-{uuid.uuid4().hex[:12]}",
            "run_id": run_id,
            "created_at": _utcnow_iso(),
            "level": "high" if impacts else "medium",
            "title": "语料维护 Agent · 法规/语料变更提醒",
            "summary": "；".join(summary_parts) or "例行扫描完成",
            "scheduled": scheduled,
            "corpus_updates": lexml_updates or list(diff.get("changed_documents") or [])[:20],
            "affected_checklist_codes": sorted(affected_codes),
            "impacted_projects": impacts,
            "feed_scan": {
                "scanned_at": feed.get("scanned_at"),
                "unreachable_sources": feed.get("unreachable_sources") or [],
            },
            "reindex": reindex_result,
            "suggested_actions": [
                "工作台查看受影响项目与文件清单",
                "对 HIGH 项目发起增量协查或合同/尽调重跑",
                "已定稿底稿不会自动修改，须法务确认后重跑",
            ],
            "acknowledged": False,
        }
        new_notifications.append(notif)
        notifications = (new_notifications + notifications)[:40]

    agent_runs = [{"run_id": run_id, "started_at": started, "finished_at": _utcnow_iso(), "scheduled": scheduled}]
    agent_runs = (agent_runs + list(state.get("agent_runs") or []))[:20]

    state["agent_notifications"] = notifications
    state["agent_runs"] = agent_runs
    state["last_agent_run_at"] = _utcnow_iso()
    _save_state(state)

    return {
        "run_id": run_id,
        "started_at": started,
        "scheduled": scheduled,
        "lexml_synced": len(lexml_updates),
        "diff": diff,
        "impacted_project_count": len(impacts),
        "impacted_projects": impacts,
        "new_notifications": new_notifications,
        "notifications": notifications[:10],
        "reindex": reindex_result,
        "feed": feed,
        "pending_review_queued": queued,
    }


def get_agent_status() -> dict[str, Any]:
    settings = get_settings()
    state = _load_state()
    notifications = list(state.get("agent_notifications") or [])
    unread = [n for n in notifications if not n.get("acknowledged")]
    return {
        "enabled": True,
        "interval_hours": AGENT_INTERVAL_HOURS,
        "last_run_at": state.get("last_agent_run_at"),
        "recent_runs": (state.get("agent_runs") or [])[:5],
        "notification_count": len(notifications),
        "unread_count": len(unread),
        "notifications": notifications[:15],
        "note": (
            "后台 Agent：定期扫描 Reg Feed、从 LexML 回溯更新语料、"
            "分析协查/合同/尽调受影响范围并推送法务通知；不自动改写已定稿。"
        ),
        "retrieval_top_k_default": settings.retrieval_top_k_default,
    }


def acknowledge_notification(notification_id: str) -> dict[str, Any]:
    state = _load_state()
    notifications = list(state.get("agent_notifications") or [])
    found = False
    for item in notifications:
        if item.get("id") == notification_id:
            item["acknowledged"] = True
            item["acknowledged_at"] = _utcnow_iso()
            found = True
            break
    if not found:
        return {"status": "error", "message": "通知不存在"}
    state["agent_notifications"] = notifications
    _save_state(state)
    return {"status": "ok", "notification_id": notification_id}
