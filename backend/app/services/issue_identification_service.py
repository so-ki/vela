"""B1 — LLM issue identification with grounding harness (Stage C)."""

from __future__ import annotations

import json
from typing import Any, Optional

from app.models.scenario import InvestigationScenario
from app.services.grounding_utils import verify_snippet_in_source
from app.services.llm_client import chat_completion_json, is_llm_enabled
from app.services.rules_registry import load_rules as load_rules_pack

ISSUE_SYSTEM = """你是 Vela 出海法务平台的议题识别助手。
任务：根据项目材料，从给定 checklist code 列表中建议可能需要增加的核查项。

硬性规则：
1. 仅输出 JSON，格式 {"suggestions":[{"code":"","title":"","confidence":"high|medium|low","fact_anchor":"","rationale":""}]}
2. code 必须来自用户提供的合法 code 列表，不得编造
3. 每条必须有 fact_anchor（材料原文短引 ≤60 字）
4. 不得新增法条名称、条文号、LexML URL 或法律结论
5. 若无合适建议，返回 {"suggestions":[]}"""


def _valid_checklist_codes(pack_id: str) -> dict[str, str]:
    rules = load_rules_pack(pack_id)
    mapping: dict[str, str] = {}
    for item in rules.get("checklist_items") or []:
        cid = item.get("id")
        if cid:
            mapping[cid] = item.get("title", cid)
    return mapping


def _material_summary(scenario: InvestigationScenario, payload: dict[str, Any], limit: int = 8000) -> str:
    parts = [
        f"项目: {scenario.project_name}",
        f"描述: {scenario.description or ''}",
        f"投资结构: {scenario.investment_structure or ''}",
        f"目的地: {scenario.investment_destination or ''}",
        f"规模: {scenario.facility_notes or ''} {scenario.capacity_notes or ''}",
        f"风险: {scenario.known_risks or ''}",
    ]
    doc = payload.get("document_extract") or {}
    facts = doc.get("facts") or []
    for fact in facts[:20]:
        parts.append(f"[{fact.get('field')}] {fact.get('value')} — {fact.get('source_snippet') or ''}")
    return "\n".join(parts)[:limit]


def _full_source_text(payload: dict[str, Any], scenario: InvestigationScenario) -> str:
    parts = [_material_summary(scenario, payload, limit=12000)]
    texts = payload.get("_material_full_texts") or {}
    if isinstance(texts, dict):
        parts.extend(str(v) for v in texts.values())
    return "\n".join(parts)


def run_issue_identification(
    scenario: InvestigationScenario,
    payload: dict[str, Any],
    *,
    user_id: Optional[int] = None,
) -> dict[str, Any]:
    pack_id = scenario.rules_pack_id or "brazil_new_energy"
    code_map = _valid_checklist_codes(pack_id)
    if not code_map:
        return {"suggestions": [], "agent_step": {"step": "issue_identification", "status": "skipped", "reason": "no codes"}}

    if not is_llm_enabled(user_id):
        return {
            "suggestions": [],
            "agent_step": {"step": "issue_identification", "status": "skipped", "reason": "llm_disabled"},
        }

    summary = _material_summary(scenario, payload)
    full_text = _full_source_text(payload, scenario)
    codes_list = sorted(code_map.keys())
    user_prompt = (
        f"合法 code 列表（仅可从中选择）：\n{json.dumps(codes_list, ensure_ascii=False)}\n\n"
        f"材料摘要：\n{summary}\n\n"
        "请返回 suggestions JSON。"
    )

    parsed, err = chat_completion_json(user_id, "issue_id", ISSUE_SYSTEM, user_prompt, timeout=90.0)
    if err or not parsed:
        return {
            "suggestions": [],
            "agent_step": {"step": "issue_identification", "status": "error", "error": err or "parse failed"},
        }

    raw_suggestions = parsed.get("suggestions") or []
    validated: list[dict[str, Any]] = []
    for item in raw_suggestions:
        if not isinstance(item, dict):
            continue
        code = str(item.get("code") or "").strip()
        if code not in code_map:
            continue
        anchor = str(item.get("fact_anchor") or "").strip()
        if not anchor:
            continue
        grounding = verify_snippet_in_source(anchor, full_text)
        if not grounding.get("grounded"):
            continue
        conf = str(item.get("confidence") or "medium").lower()
        if conf not in ("high", "medium", "low"):
            conf = "medium"
        validated.append(
            {
                "code": code,
                "title": item.get("title") or code_map[code],
                "confidence": conf,
                "fact_anchor": anchor,
                "rationale": str(item.get("rationale") or "")[:300],
                "grounding_score": grounding.get("grounding_score"),
            }
        )

    status = "ok" if validated else "empty"
    return {
        "suggestions": validated,
        "agent_step": {"step": "issue_identification", "status": status, "count": len(validated)},
    }
