"""B3 — LLM gap explanations / follow-up questions (no new statutes)."""

from __future__ import annotations

import json
from typing import Any, Optional

from app.models.scenario import InvestigationScenario
from app.services.llm_client import chat_completion_json, is_llm_enabled
from app.services.rules_registry import load_rules as load_rules_pack

GAP_SYSTEM = """你是 Vela 出海法务平台的材料缺口说明助手。
任务：针对未通过门控或构成要件 missing/at_risk 的核查项，生成向业务追问的问题清单。

硬性规则：
1. 仅输出 JSON：{"items":[{"code":"","questions_zh":[],"questions_pt":[],"material_gaps":[],"suggested_documents":[]}]}
2. 禁止出现具体法条号、法律结论、LexML URL
3. 仅基于给定 code 与 rationale 提问，不得编造新核查项
4. questions 应为开放式问题，供业务补充材料"""


def _checklist_meta(pack_id: str) -> dict[str, dict[str, str]]:
    rules = load_rules_pack(pack_id)
    return {
        item["id"]: {
            "title": item.get("title", item["id"]),
            "description": item.get("description", ""),
        }
        for item in (rules.get("checklist_items") or [])
        if item.get("id")
    }


def _template_fallback(code: str, meta: dict[str, str], rationale: str) -> dict[str, Any]:
    title = meta.get("title", code)
    desc = meta.get("description", "")
    return {
        "code": code,
        "questions_zh": [
            f"请补充与「{title}」相关的项目事实与支撑材料。",
            f"当前缺口：{rationale or desc[:120]}",
        ],
        "questions_pt": [
            f"Por favor, complemente fatos e documentos relacionados a «{title}».",
        ],
        "material_gaps": [rationale or desc[:160]],
        "suggested_documents": ["项目方案补充说明", "相关承诺/批复复印件（如有）"],
        "mode": "template",
    }


def _targets_from_payload(checklist_payload: dict[str, Any], adequacy: dict[str, Any]) -> list[dict[str, Any]]:
    targets: list[dict[str, Any]] = []
    brief = checklist_payload.get("brief") or {}
    blocked_codes = {
        item.get("code")
        for section in brief.get("sections") or []
        for item in section.get("items") or []
        if item.get("gate_status") != "passed" and item.get("code")
    }

    for dim in adequacy.get("dimensions") or []:
        for el in dim.get("elements") or []:
            if el.get("status") in ("missing", "at_risk"):
                for code in el.get("linked_codes") or []:
                    if code in blocked_codes or el.get("status") == "missing":
                        targets.append(
                            {
                                "code": code,
                                "rationale": el.get("rationale") or "",
                                "element_id": el.get("id"),
                            }
                        )

    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for t in targets:
        c = t["code"]
        if c in seen:
            continue
        seen.add(c)
        unique.append(t)
    return unique[:12]


def run_gap_explanations(
    scenario: InvestigationScenario,
    checklist_payload: dict[str, Any],
    *,
    user_id: Optional[int] = None,
) -> dict[str, Any]:
    adequacy = checklist_payload.get("investigation_adequacy") or {}
    pack_id = scenario.rules_pack_id or "brazil_new_energy"
    meta = _checklist_meta(pack_id)
    targets = _targets_from_payload(checklist_payload, adequacy)

    if not targets:
        return {
            "items": [],
            "agent_step": {"step": "gap_explanation", "status": "skipped", "count": 0},
        }

    if not is_llm_enabled(user_id):
        items = [_template_fallback(t["code"], meta.get(t["code"], {}), t["rationale"]) for t in targets]
        return {
            "items": items,
            "agent_step": {"step": "gap_explanation", "status": "fallback", "count": len(items)},
        }

    prompt_items = [
        {"code": t["code"], "title": meta.get(t["code"], {}).get("title", t["code"]), "rationale": t["rationale"]}
        for t in targets
    ]
    user_prompt = f"请为以下条目生成缺口说明 JSON：\n{json.dumps(prompt_items, ensure_ascii=False)}"
    parsed, err = chat_completion_json(user_id, "gap", GAP_SYSTEM, user_prompt, timeout=90.0)

    if err or not parsed:
        items = [_template_fallback(t["code"], meta.get(t["code"], {}), t["rationale"]) for t in targets]
        return {
            "items": items,
            "agent_step": {"step": "gap_explanation", "status": "fallback", "error": err},
        }

    by_code = {str(i.get("code")): i for i in (parsed.get("items") or []) if i.get("code")}
    items: list[dict[str, Any]] = []
    for t in targets:
        code = t["code"]
        raw = by_code.get(code)
        if not raw:
            items.append(_template_fallback(code, meta.get(code, {}), t["rationale"]))
            continue
        items.append(
            {
                "code": code,
                "questions_zh": list(raw.get("questions_zh") or [])[:6],
                "questions_pt": list(raw.get("questions_pt") or [])[:6],
                "material_gaps": list(raw.get("material_gaps") or [])[:4],
                "suggested_documents": list(raw.get("suggested_documents") or [])[:4],
                "mode": "llm",
            }
        )

    return {
        "items": items,
        "agent_step": {"step": "gap_explanation", "status": "ok", "count": len(items)},
    }
