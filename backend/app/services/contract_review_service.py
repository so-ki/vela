"""Contract review: structured Playbook + grounding + Red Team (Claude/Lavern patterns)."""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from app.services.cold_start_service import profile_for_generation
from app.services.contract_house_rules_service import (
    load_structured_house_rules,
    merge_profile_house_rules,
    phrase_hits,
    rule_detected,
)
from app.services.document_extractor import read_upload_text
from app.services.project_hub_service import link_contract_to_investigation, project_context
from app.services.user_preference_service import record_contract_finding_decision


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _split_clauses(text: str) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    parts = re.split(
        r"\n(?=\s*(?:Art\.|Artigo|Cláusula|CLAUSE|第\s*\d+|Section\s+\d+|\d+\.\s))",
        text,
        flags=re.I,
    )
    if len(parts) <= 1:
        parts = [p.strip() for p in re.split(r"\n{2,}", text) if len(p.strip()) > 40]
    for idx, part in enumerate(parts[:80]):
        part = part.strip()
        if len(part) < 30:
            continue
        chunks.append({"index": idx + 1, "text": part[:3000], "excerpt": part[:400]})
    if not chunks and text.strip():
        chunks.append({"index": 1, "text": text[:3000], "excerpt": text[:400]})
    return chunks


def _ground_span(clause_text: str, anchor: str) -> dict[str, Any]:
    anchor = (anchor or "").strip()
    if not anchor:
        return {"grounded": False, "grounding_span": "", "grounding_note": "无锚定摘录"}
    lower_c = clause_text.lower()
    lower_a = anchor.lower()
    if lower_a in lower_c:
        start = lower_c.index(lower_a)
        span = clause_text[start : start + min(len(anchor) + 40, 200)]
        return {"grounded": True, "grounding_span": span.strip(), "grounding_note": None}
    if clause_text[:200].lower() in lower_c or lower_c[:200] in lower_a:
        return {"grounded": True, "grounding_span": clause_text[:200].strip(), "grounding_note": None}
    return {
        "grounded": False,
        "grounding_span": clause_text[:120].strip(),
        "grounding_note": "结论锚定待法务核对原文",
    }


def _evaluate_structured_rule(clause_text: str, rule: dict[str, Any]) -> Optional[dict[str, Any]]:
    if not rule_detected(clause_text, rule):
        return None

    must_not_hits = phrase_hits(clause_text, rule.get("must_not") or [])
    must_have_hits = phrase_hits(clause_text, rule.get("must_have") or [])
    exception_hits = phrase_hits(clause_text, rule.get("exceptions") or [])

    issues: list[dict[str, Any]] = []
    risk = "YELLOW"
    risk_label = "命中 Playbook · 须法务确认"
    tier = "S2"

    if must_not_hits and not exception_hits:
        risk = "RED"
        risk_label = "违反 must_not 底线"
        tier = "S3"
        issues.append({"type": "must_not_violation", "phrases": must_not_hits})
        anchor = must_not_hits[0]
    elif must_not_hits and exception_hits:
        risk = "YELLOW"
        risk_label = "命中禁止表述但有例外线索 · 须确认"
        tier = "S2"
        issues.append({"type": "exception_may_apply", "phrases": exception_hits})
        anchor = must_not_hits[0]
    elif rule.get("must_have") and not must_have_hits:
        risk = "YELLOW"
        risk_label = "缺少 must_have 必备要件"
        tier = "S2"
        issues.append({"type": "must_have_missing", "expected": rule.get("must_have") or []})
        anchor = clause_text[:120]
    else:
        issues.append({"type": "keyword_hit_only", "note": "仅关键词命中，需结合上下文"})
        anchor = clause_text[:120]

    grounding = _ground_span(clause_text, anchor)
    if risk == "RED" and not grounding["grounded"]:
        risk = "YELLOW"
        risk_label = "疑似红线但未 grounding · 降级为须确认"
        tier = "S2"
        issues.append({"type": "red_downgrade_no_grounding"})

    return {
        "rule_id": rule["id"],
        "label": rule["label"],
        "severity": rule.get("severity", "medium"),
        "risk": risk,
        "risk_label": risk_label,
        "tier": tier,
        "issues": issues,
        "must_have_satisfied": bool(must_have_hits) if rule.get("must_have") else None,
        "must_not_hits": must_not_hits,
        "guidance": rule.get("guidance", ""),
        "grounded": grounding["grounded"],
        "grounding_span": grounding["grounding_span"],
        "grounding_note": grounding["grounding_note"],
    }


def _merge_rule_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    if not results:
        return {
            "risk": "GREEN",
            "risk_label": "未发现 Playbook 关注点",
            "matched_rules": [],
            "tier": "S1",
            "issues": [],
            "grounded": True,
        }
    order = {"RED": 3, "YELLOW": 2, "GREEN": 1}
    results.sort(key=lambda r: order.get(r["risk"], 0), reverse=True)
    top = results[0]
    return {
        "risk": top["risk"],
        "risk_label": top["risk_label"],
        "tier": top["tier"],
        "matched_rules": [
            {
                "id": r["rule_id"],
                "label": r["label"],
                "severity": r["severity"],
                "issues": r["issues"],
            }
            for r in results
        ],
        "issues": top["issues"],
        "grounded": all(r.get("grounded") for r in results if r["risk"] != "GREEN"),
        "grounding_span": top.get("grounding_span"),
        "grounding_note": top.get("grounding_note"),
        "must_have_satisfied": top.get("must_have_satisfied"),
    }


def _run_contract_red_team(
    findings: list[dict[str, Any]],
    clauses: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Challenge false positives and cross-clause contradictions."""
    challenges: list[dict[str, Any]] = []

    by_rule: dict[str, list[dict[str, Any]]] = {}
    for f in findings:
        for mr in f.get("matched_rules") or []:
            by_rule.setdefault(mr.get("id") or "", []).append(f)

    for rule_id, group in by_rule.items():
        if not rule_id or len(group) < 2:
            continue
        risks = {g.get("risk") for g in group}
        if "RED" in risks and "GREEN" in risks:
            challenges.append(
                {
                    "type": "cross_clause_contradiction",
                    "rule_id": rule_id,
                    "severity": "high",
                    "message": f"规则 {rule_id}：部分条款 RED、部分 GREEN，存在跨条款矛盾",
                    "clause_indices": [g.get("clause_index") for g in group],
                }
            )

    for f in findings:
        if f.get("risk") != "RED":
            continue
        if f.get("must_have_satisfied") is True:
            f["risk"] = "YELLOW"
            f["risk_label"] = "Red Team：已含 must_have，降级为须确认"
            f["tier"] = "S2"
            f["red_team_note"] = "must_have 已满足，避免误报 RED"
            challenges.append(
                {
                    "type": "false_positive_downgrade",
                    "rule_id": (f.get("matched_rules") or [{}])[0].get("id"),
                    "severity": "medium",
                    "message": f"条款 #{f.get('clause_index')} RED 降级为 YELLOW（must_have 已满足）",
                    "clause_index": f.get("clause_index"),
                }
            )

    liability_red = [f for f in findings if f.get("risk") == "RED" and any(
        m.get("id") == "liability_cap" for m in (f.get("matched_rules") or [])
    )]
    lgpd_yellow = [f for f in findings if any(
        m.get("id") == "lgpd_dpa" for m in (f.get("matched_rules") or [])
    )]
    if liability_red and not lgpd_yellow and len(clauses) > 3:
        challenges.append(
            {
                "type": "possible_miss",
                "rule_id": "lgpd_dpa",
                "severity": "low",
                "message": "Red Team：合同较长且有责任条款，但未扫描到 LGPD/数据条款，建议人工补查",
            }
        )

    return challenges


def upload_contract_document(
    payload: dict[str, Any],
    *,
    filename: str,
    content: bytes,
    contract_type: str = "general",
) -> dict[str, Any]:
    from app.services.project_hub_service import ensure_project_hub

    ensure_project_hub(payload)
    doc_id = uuid.uuid4().hex[:16]
    text = read_upload_text(filename, content)
    doc = {
        "id": doc_id,
        "filename": filename,
        "contract_type": contract_type,
        "size": len(content),
        "char_count": len(text),
        "uploaded_at": _utcnow_iso(),
        "status": "uploaded",
        "text_preview": text[:500],
    }
    payload["project_hub"]["modules"]["contracts"].setdefault("documents", []).append(doc)
    payload.setdefault("_contract_texts", {})[doc_id] = text
    payload["project_hub"]["modules"]["contracts"]["status"] = "uploaded"
    return doc


def analyze_contract(
    payload: dict[str, Any],
    scenario: Any,
    *,
    doc_id: str,
    user_id: Optional[int] = None,
) -> dict[str, Any]:
    from app.services.project_hub_service import ensure_project_hub

    ensure_project_hub(payload)
    texts = payload.get("_contract_texts") or {}
    text = texts.get(doc_id)
    if not text:
        docs = payload["project_hub"]["modules"]["contracts"].get("documents") or []
        if not next((d for d in docs if d.get("id") == doc_id), None):
            raise ValueError(f"合同文档不存在: {doc_id}")
        raise ValueError("合同正文未缓存，请重新上传")

    profile = profile_for_generation(user_id)
    house_rules = merge_profile_house_rules(
        load_structured_house_rules(),
        profile.get("contract_house_rules") or "",
    )

    ctx = project_context(payload, scenario)
    clauses = _split_clauses(text)
    findings: list[dict[str, Any]] = []
    red = yellow = green = 0

    for clause in clauses:
        rule_results = [_evaluate_structured_rule(clause["text"], rule) for rule in house_rules]
        rule_results = [r for r in rule_results if r]
        classification = _merge_rule_results(rule_results)
        inv_note = _cross_investigation_note(classification, ctx)
        finding = {
            "clause_index": clause["index"],
            "excerpt": clause["excerpt"],
            "risk": classification["risk"],
            "risk_label": classification["risk_label"],
            "tier": classification.get("tier", "S2"),
            "matched_rules": classification["matched_rules"],
            "issues": classification.get("issues") or [],
            "grounded": classification.get("grounded", False),
            "grounding_span": classification.get("grounding_span"),
            "grounding_note": classification.get("grounding_note"),
            "must_have_satisfied": classification.get("must_have_satisfied"),
            "investigation_link": inv_note,
            "requires_review": classification["risk"] != "GREEN" or not classification.get("grounded"),
        }
        findings.append(finding)
        if classification["risk"] == "RED":
            red += 1
        elif classification["risk"] == "YELLOW":
            yellow += 1
        else:
            green += 1

    red_team_challenges = _run_contract_red_team(findings, clauses)
    red = sum(1 for f in findings if f.get("risk") == "RED")
    yellow = sum(1 for f in findings if f.get("risk") == "YELLOW")
    green = sum(1 for f in findings if f.get("risk") == "GREEN")

    summary = {
        "doc_id": doc_id,
        "analyzed_at": _utcnow_iso(),
        "total_clauses": len(findings),
        "red_count": red,
        "yellow_count": yellow,
        "green_count": green,
        "project_context_used": True,
        "house_rules_source": "structured_playbook_v1",
        "house_rules_profile": bool(profile.get("completed")),
        "review_mode": "structured_must_have_must_not + grounding + red_team",
        "red_team_challenge_count": len(red_team_challenges),
        "disclaimer": "合同审查为 AI 辅助草稿；RED/S3 须律师 grounding 确认后方可作为签署建议。",
    }

    for doc in payload["project_hub"]["modules"]["contracts"].get("documents") or []:
        if doc.get("id") == doc_id:
            doc["status"] = "analyzed"
            doc["analysis"] = summary
            doc["findings"] = findings
            doc["red_team_challenges"] = red_team_challenges
            break

    payload["project_hub"]["modules"]["contracts"]["status"] = "analyzed"
    payload["project_hub"]["modules"]["contracts"]["last_analyzed_at"] = summary["analyzed_at"]
    payload.setdefault("contract_analyses", {})[doc_id] = {
        "summary": summary,
        "findings": findings,
        "red_team_challenges": red_team_challenges,
    }

    if red > 0:
        link_contract_to_investigation(
            payload,
            doc_id,
            f"合同审查发现 {red} 条 RED 条款（结构化 Playbook + Red Team），建议与协查 S3 交叉核对",
        )
    return {"summary": summary, "findings": findings, "red_team_challenges": red_team_challenges}


def review_contract_finding(
    payload: dict[str, Any],
    *,
    doc_id: str,
    clause_index: int,
    decision: str,
    user_id: int,
    comment: Optional[str] = None,
) -> dict[str, Any]:
    """Legal confirm/reject on a clause finding — feeds preference loop."""
    stored = payload.setdefault("contract_analyses", {}).get(doc_id)
    if not stored:
        raise ValueError("尚未分析该合同")

    finding = next(
        (f for f in stored.get("findings") or [] if f.get("clause_index") == clause_index),
        None,
    )
    if not finding:
        raise ValueError(f"条款 #{clause_index} 不存在")

    rule_id = (finding.get("matched_rules") or [{}])[0].get("id") or "general"
    record_contract_finding_decision(
        user_id,
        rule_id=rule_id,
        clause_index=clause_index,
        decision=decision,
        comment=comment,
        risk=finding.get("risk"),
    )
    finding["legal_decision"] = decision
    finding["legal_comment"] = (comment or "")[:500]
    finding["reviewed_at"] = _utcnow_iso()

    reviews = payload.setdefault("contract_finding_reviews", {}).setdefault(doc_id, [])
    reviews.insert(
        0,
        {
            "clause_index": clause_index,
            "rule_id": rule_id,
            "decision": decision,
            "comment": comment,
            "at": finding["reviewed_at"],
        },
    )
    payload["contract_finding_reviews"][doc_id] = reviews[:100]
    return finding


def _cross_investigation_note(classification: dict[str, Any], ctx: dict[str, Any]) -> Optional[str]:
    if classification["risk"] == "GREEN":
        return None
    s3 = ctx.get("investigation_summary", {}).get("s3_blocked_codes") or []
    if s3:
        return f"投资协查存在 S3 条目 {', '.join(s3[:4])}，请与合同条款一并评估"
    for rule in classification.get("matched_rules") or []:
        if rule.get("id") == "lgpd_dpa":
            return "建议对照 DAT-* 核查项与 LGPD 协查结论"
    return "可结合本项目投资协查清单交叉验证"


def get_contract_analysis(payload: dict[str, Any], doc_id: str) -> dict[str, Any]:
    stored = (payload.get("contract_analyses") or {}).get(doc_id)
    if stored:
        return stored
    for doc in (payload.get("project_hub") or {}).get("modules", {}).get("contracts", {}).get("documents") or []:
        if doc.get("id") == doc_id and doc.get("findings"):
            return {
                "summary": doc.get("analysis"),
                "findings": doc.get("findings"),
                "red_team_challenges": doc.get("red_team_challenges") or [],
            }
    raise ValueError("尚未分析该合同")
