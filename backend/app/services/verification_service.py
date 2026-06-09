"""Multi-pass verification (Lavern-inspired, simplified for协查包)."""

from __future__ import annotations

from typing import Any


def run_brief_verification_passes(
    payload: dict[str, Any],
    brief: dict[str, Any],
) -> dict[str, Any]:
    """Three passes: accuracy (grounding), completeness (coverage), risk (blocked high-priority)."""
    grounding = payload.get("grounding_report") or {}
    sections = payload.get("sections_with_legal") or payload.get("sections") or []
    all_items: list[dict[str, Any]] = []
    for section in brief.get("sections") or []:
        all_items.extend(section.get("items") or [])

    # Pass 1 — accuracy: grounding + passed items should have hits
    ungrounded = set(grounding.get("ungrounded_codes") or [])
    passed_without_ground = [
        i["code"]
        for i in all_items
        if i.get("gate_status") == "passed" and i.get("code") in ungrounded
    ]
    accuracy_ok = not passed_without_ground and grounding.get("grounding_rate", 1.0) >= 0.8

    # Pass 2 — completeness: zero-hit checklist codes in scope
    zero_hits = set()
    for section in sections:
        for item in section.get("items", []):
            if not item.get("legal_hits"):
                zero_hits.add(item.get("code"))
    completeness_ok = len(zero_hits) == 0

    # Pass 3 — risk: high-priority blocked
    blocked_high = [
        i["code"]
        for i in all_items
        if i.get("gate_status") != "passed" and i.get("priority") == "high"
    ]
    risk_ok = len(blocked_high) == 0

    passes = [
        {
            "id": "accuracy",
            "label": "引证准确性",
            "passed": accuracy_ok,
            "detail": (
                "Top 法条摘录与语料一致"
                if accuracy_ok
                else f"以下已通过条目引证待核：{', '.join(passed_without_ground[:6]) or 'grounding_rate 偏低'}"
            ),
        },
        {
            "id": "completeness",
            "label": "检索完整性",
            "passed": completeness_ok,
            "detail": (
                "清单条目均有法源命中"
                if completeness_ok
                else f"零命中条目：{', '.join(sorted(c for c in zero_hits if c)[:8])}"
            ),
        },
        {
            "id": "risk",
            "label": "高风险门控",
            "passed": risk_ok,
            "detail": (
                "无高优先级门控未过条目"
                if risk_ok
                else f"高优先级 blocked：{', '.join(blocked_high[:6])}"
            ),
        },
    ]

    all_passed = all(p["passed"] for p in passes)
    return {
        "passes": passes,
        "all_passed": all_passed,
        "blocked_export_recommendation": not all_passed,
        "summary": "三 pass 验证通过" if all_passed else "存在待法务确认的验证项",
    }
