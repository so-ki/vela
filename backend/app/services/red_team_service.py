"""B4 — Investigation Red Team for S2 items only (questions, no tier change)."""

from __future__ import annotations

import json
from typing import Any, Optional

from app.services.llm_client import chat_completion_json, is_llm_enabled

RED_TEAM_SYSTEM = """你是 Vela 出海法务平台的 Red Team 助手（协查条目质疑）。
任务：针对 S2 核查条目，基于材料与已有法条命中，提出质疑性问题供法务复核。

硬性规则：
1. 仅输出 JSON：{"challenges":[{"code":"","questions":[{"question":"","severity":"high|medium|low"}],"red_team_note":""}]}
2. 不得修改 tier、gate_status、match_score
3. 不得新增法条名称/条文号/LexML URL
4. 仅输出质疑问题，不得给出法律结论"""


def _s2_items_from_payload(checklist_payload: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for section in checklist_payload.get("sections_with_legal") or []:
        for item in section.get("items") or []:
            if item.get("tier") == "S2":
                hits = item.get("legal_hits") or []
                items.append(
                    {
                        "code": item.get("code"),
                        "title": item.get("title"),
                        "description": (item.get("description") or "")[:200],
                        "match_score": item.get("match_score"),
                        "gate_status": item.get("gate_status"),
                        "legal_hit_titles": [h.get("title_zh") or h.get("title_pt") for h in hits[:2]],
                    }
                )
    return items[:15]


def run_investigation_red_team(
    checklist_payload: dict[str, Any],
    *,
    material_summary: str = "",
    user_id: Optional[int] = None,
) -> dict[str, Any]:
    s2_items = _s2_items_from_payload(checklist_payload)
    if not s2_items:
        return {
            "challenges": [],
            "agent_step": {"step": "red_team", "status": "skipped", "reason": "no_s2"},
        }

    if not is_llm_enabled(user_id):
        return {
            "challenges": [],
            "agent_step": {"step": "red_team", "status": "skipped", "reason": "llm_disabled"},
        }

    user_prompt = (
        f"材料摘要：\n{material_summary[:4000]}\n\n"
        f"S2 条目：\n{json.dumps(s2_items, ensure_ascii=False)}\n\n"
        "请返回 challenges JSON。"
    )
    parsed, err = chat_completion_json(user_id, "red_team", RED_TEAM_SYSTEM, user_prompt, timeout=90.0)
    if err or not parsed:
        return {
            "challenges": [],
            "agent_step": {"step": "red_team", "status": "error", "error": err},
        }

    valid_codes = {i["code"] for i in s2_items if i.get("code")}
    challenges: list[dict[str, Any]] = []
    for ch in parsed.get("challenges") or []:
        code = str(ch.get("code") or "").strip()
        if code not in valid_codes:
            continue
        questions = []
        for q in ch.get("questions") or []:
            if not isinstance(q, dict) or not q.get("question"):
                continue
            sev = str(q.get("severity") or "medium").lower()
            if sev not in ("high", "medium", "low"):
                sev = "medium"
            questions.append({"question": str(q["question"])[:300], "severity": sev})
        if questions:
            challenges.append(
                {
                    "code": code,
                    "questions": questions,
                    "red_team_note": str(ch.get("red_team_note") or "")[:300],
                }
            )

    return {
        "challenges": challenges,
        "agent_step": {"step": "red_team", "status": "ok" if challenges else "empty", "count": len(challenges)},
    }
