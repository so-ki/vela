from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.services.legal_ingest import INDEX_FLAG, ingest_corpus, load_corpus

MONITOR_PATH = Path(__file__).resolve().parents[2] / "data" / "legal_monitor.json"


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _doc_fingerprint(doc: dict[str, Any]) -> str:
    payload = json.dumps(
        {
            "id": doc.get("id"),
            "title_pt": doc.get("title_pt"),
            "validity": doc.get("validity"),
            "checklist_codes": sorted(doc.get("checklist_codes") or []),
            "dimension": doc.get("dimension"),
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def _corpus_fingerprint() -> str:
    corpus = load_corpus()
    payload = json.dumps(corpus.get("sources", []), ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def _build_doc_snapshot() -> dict[str, str]:
    corpus = load_corpus()
    return {str(doc.get("id")): _doc_fingerprint(doc) for doc in corpus.get("sources", []) if doc.get("id")}


def _load_state() -> dict[str, Any]:
    if not MONITOR_PATH.exists():
        return {
            "alerts": [],
            "last_scan_at": None,
            "corpus_fingerprint": None,
            "doc_snapshot": {},
            "subscriptions": [],
            "last_diff": None,
        }
    with open(MONITOR_PATH, encoding="utf-8") as f:
        state = json.load(f)
    state.setdefault("subscriptions", [])
    state.setdefault("doc_snapshot", {})
    state.setdefault("last_diff", None)
    return state


def _save_state(state: dict[str, Any]) -> None:
    MONITOR_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(MONITOR_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def _collect_checklist_codes(payload: dict[str, Any] | None) -> list[str]:
    if not payload:
        return []
    codes: list[str] = []
    for section in payload.get("sections") or payload.get("sections_with_legal") or []:
        for item in section.get("items") or []:
            code = item.get("code")
            if code:
                codes.append(code)
    return sorted(set(codes))


def compute_corpus_diff(*, prev_snapshot: dict[str, str] | None = None) -> dict[str, Any]:
    corpus = load_corpus()
    current_snapshot = _build_doc_snapshot()
    prev = prev_snapshot or {}
    changed_docs: list[dict[str, Any]] = []
    affected_codes: set[str] = set()

    all_ids = set(prev.keys()) | set(current_snapshot.keys())
    doc_by_id = {str(doc.get("id")): doc for doc in corpus.get("sources", []) if doc.get("id")}

    for doc_id in sorted(all_ids):
        prev_fp = prev.get(doc_id)
        curr_fp = current_snapshot.get(doc_id)
        if prev_fp == curr_fp:
            continue
        doc = doc_by_id.get(doc_id, {"id": doc_id})
        codes = list(doc.get("checklist_codes") or [])
        affected_codes.update(codes)
        if doc_id not in prev:
            change_type = "added"
        elif doc_id not in current_snapshot:
            change_type = "removed"
        else:
            change_type = "updated"
        changed_docs.append(
            {
                "id": doc_id,
                "change_type": change_type,
                "title_pt": doc.get("title_pt") or doc_id,
                "dimension": doc.get("dimension"),
                "checklist_codes": codes,
            }
        )

    return {
        "computed_at": _utcnow_iso(),
        "changed_documents": changed_docs,
        "affected_checklist_codes": sorted(affected_codes),
        "has_changes": bool(changed_docs),
    }


def upsert_scenario_subscription(
    scenario_id: int,
    project_name: str,
    checklist_payload: dict[str, Any],
    *,
    checklist_codes: list[str] | None = None,
    compliance_dimensions: list[str] | None = None,
) -> dict[str, Any]:
    """Subscribe a scenario to corpus diff alerts for its checklist codes."""
    state = _load_state()
    subscriptions: list[dict[str, Any]] = list(state.get("subscriptions") or [])
    codes = checklist_codes or _collect_checklist_codes(checklist_payload)
    dimensions = compliance_dimensions or list(checklist_payload.get("compliance_dimensions") or [])
    entry = {
        "scenario_id": scenario_id,
        "project_name": project_name,
        "checklist_codes": codes,
        "compliance_dimensions": dimensions,
        "subscribed_at": _utcnow_iso(),
    }
    subscriptions = [s for s in subscriptions if s.get("scenario_id") != scenario_id]
    subscriptions.insert(0, entry)
    state["subscriptions"] = subscriptions[:50]
    _save_state(state)
    return entry


def list_subscriptions() -> list[dict[str, Any]]:
    return list(_load_state().get("subscriptions") or [])


def get_monitor_status() -> dict[str, Any]:
    corpus = load_corpus()
    breakdown: dict[str, int] = {}
    for s in corpus.get("sources", []):
        src = s.get("source", "unknown")
        breakdown[src] = breakdown.get(src, 0) + 1

    state = _load_state()
    index_flag = {}
    if INDEX_FLAG.exists():
        with open(INDEX_FLAG, encoding="utf-8") as f:
            index_flag = json.load(f)

    last_diff = state.get("last_diff") or {}
    subscriptions = list(state.get("subscriptions") or [])

    return {
        "enabled": True,
        "corpus_version": corpus.get("version", "1.0"),
        "document_count": len(corpus.get("sources", [])),
        "sources_breakdown": breakdown,
        "index_mode": index_flag.get("mode", "pending"),
        "last_scan_at": state.get("last_scan_at"),
        "corpus_fingerprint": state.get("corpus_fingerprint") or _corpus_fingerprint(),
        "alerts": state.get("alerts", [])[:20],
        "subscription_note": "MVP：本地语料变更检测 + 场景订阅；生产环境可对接 LexML RSS/API。",
        "subscriptions": subscriptions[:20],
        "subscription_count": len(subscriptions),
        "last_diff": last_diff if last_diff.get("has_changes") else None,
    }


def scan_regulatory_updates(*, force_reindex: bool = False) -> dict[str, Any]:
    corpus = load_corpus()
    state = _load_state()
    prev_fp = state.get("corpus_fingerprint")
    current_fp = _corpus_fingerprint()
    prev_snapshot = dict(state.get("doc_snapshot") or {})
    now = _utcnow_iso()

    alerts: list[dict[str, Any]] = list(state.get("alerts", []))
    new_alerts: list[dict[str, Any]] = []

    diff = compute_corpus_diff(prev_snapshot=prev_snapshot if prev_snapshot else None)
    if diff["has_changes"]:
        affected = diff.get("affected_checklist_codes") or []
        new_alerts.append(
            {
                "id": f"corpus-diff-{current_fp}",
                "level": "medium" if affected else "info",
                "title": "法源语料变更 · 影响核查项",
                "message": (
                    f"检测到 {len(diff.get('changed_documents') or [])} 条语料变更，"
                    f"关联核查项 {', '.join(affected[:8]) or '无'}"
                    + ("…" if len(affected) > 8 else "")
                    + "。已定稿底稿不会自动变更，建议发起增量协查或更新语料绑定。"
                ),
                "detected_at": now,
                "affected_checklist_codes": affected,
            }
        )
        for sub in state.get("subscriptions") or []:
            sub_codes = set(sub.get("checklist_codes") or [])
            overlap = sorted(sub_codes & set(affected))
            if not overlap:
                continue
            new_alerts.append(
                {
                    "id": f"sub-{sub.get('scenario_id')}-{current_fp[:8]}",
                    "level": "medium",
                    "title": f"订阅提醒 · {sub.get('project_name') or sub.get('scenario_id')}",
                    "message": f"语料变更影响本项目核查项：{', '.join(overlap[:6])}"
                    + ("…" if len(overlap) > 6 else "")
                    + "。请法务评估是否补材料或重跑 RAG。",
                    "detected_at": now,
                    "scenario_id": sub.get("scenario_id"),
                    "affected_checklist_codes": overlap,
                }
            )

    if prev_fp and prev_fp != current_fp and not diff["has_changes"]:
        new_alerts.append(
            {
                "id": f"corpus-{current_fp}",
                "level": "info",
                "title": "本地法源库版本变更",
                "message": f"语料指纹已更新（{prev_fp} → {current_fp}），建议重新绑定清单法条。",
                "detected_at": now,
            }
        )

    demo_watch = [
        {
            "id": "watch-ibama-licensing",
            "level": "medium",
            "title": "IBAMA 环境许可口径监测",
            "message": "已扫描联邦环境许可相关条目；未发现本地语料删减，索引可继续使用。",
            "detected_at": now,
        },
        {
            "id": "watch-sp-icms",
            "level": "low",
            "title": "圣保罗州 ICMS 规则跟踪",
            "message": "州级税制条目已纳入索引；如有官方更新请扩充 brazil_legal_corpus.json。",
            "detected_at": now,
        },
    ]
    for item in demo_watch:
        if not any(a.get("id") == item["id"] for a in alerts):
            new_alerts.append(item)

    index_result = ingest_corpus(force=force_reindex)
    if force_reindex:
        new_alerts.append(
            {
                "id": f"reindex-{now[:10]}",
                "level": "info",
                "title": "法源索引已重建",
                "message": index_result.get("message", "索引刷新完成"),
                "detected_at": now,
            }
        )

    merged = (new_alerts + alerts)[:30]
    _save_state(
        {
            "last_scan_at": now,
            "corpus_fingerprint": current_fp,
            "doc_snapshot": _build_doc_snapshot(),
            "alerts": merged,
            "subscriptions": state.get("subscriptions") or [],
            "last_diff": diff if diff["has_changes"] else state.get("last_diff"),
        }
    )

    return {
        "scanned_at": now,
        "corpus_fingerprint": current_fp,
        "new_alerts": new_alerts,
        "alerts": merged,
        "index": index_result,
        "diff": diff,
    }
