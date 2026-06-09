"""Legal-Skills-inspired match tiers: S1 auto / S2 review / S3 hard block."""

from __future__ import annotations

from typing import Any, Optional

TIER_S1 = "S1"
TIER_S2 = "S2"
TIER_S3 = "S3"

TIER_LABELS = {
    TIER_S1: "自动通过",
    TIER_S2: "人工复核",
    TIER_S3: "硬阻断",
}


def _priority_floor(priority: str) -> int:
    return {"high": 75, "medium": 70, "low": 65}.get(priority, 70)


def _effective_threshold(
    *,
    base_threshold: int,
    priority: str,
    user_adjustment: int = 0,
) -> int:
    floor = _priority_floor(priority)
    return max(50, min(95, max(base_threshold, floor) + user_adjustment))


def classify_item_tier(
    *,
    item_code: str,
    priority: str,
    match_score: float,
    legal_hits: list[dict[str, Any]],
    grounded: bool = True,
    base_threshold: int = 70,
    user_adjustment: int = 0,
) -> dict[str, Any]:
    """Composite gate inspired by Legal-Skills atomic skills (retrieve → validate → classify)."""
    threshold = _effective_threshold(
        base_threshold=base_threshold,
        priority=priority,
        user_adjustment=user_adjustment,
    )
    has_hits = bool(legal_hits)
    score = float(match_score or 0)

    if not has_hits:
        tier = TIER_S3
        reason = "未检索到法条片段"
    elif not grounded and priority == "high":
        tier = TIER_S3
        reason = "高优先级条目引证未通过 grounding 校验"
    elif score < threshold - 15 and priority == "high":
        tier = TIER_S3
        reason = f"高优先级匹配度 {score:.0f} 低于硬阻断线 {threshold - 15}"
    elif score >= threshold and grounded:
        tier = TIER_S1
        reason = None
    elif score >= threshold - 10 and has_hits:
        tier = TIER_S2
        reason = f"匹配度 {score:.0f} 接近阈值 {threshold}，建议法务确认"
    else:
        tier = TIER_S2 if priority != "high" else TIER_S3
        reason = f"匹配度 {score:.0f} 低于阈值 {threshold}"

    hard_block = tier == TIER_S3
    gate_status = "passed" if tier == TIER_S1 else "blocked"

    return {
        "code": item_code,
        "tier": tier,
        "tier_label": TIER_LABELS[tier],
        "hard_block": hard_block,
        "gate_status": gate_status,
        "effective_threshold": threshold,
        "match_score": score,
        "grounded": grounded,
        "block_reason": reason,
        "requires_review": tier != TIER_S1,
        "human_review_hint": reason or "可纳入自动简报",
    }


def classify_sections(
    sections: list[dict[str, Any]],
    *,
    base_threshold: int = 70,
    grounding_report: Optional[dict[str, Any]] = None,
    user_threshold_adjustments: Optional[dict[str, int]] = None,
) -> dict[str, Any]:
    ungrounded = set((grounding_report or {}).get("ungrounded_codes") or [])
    adjustments = user_threshold_adjustments or {}

    tiered_sections: list[dict[str, Any]] = []
    s1 = s2 = s3 = 0
    s3_codes: list[str] = []

    for section in sections:
        items_out: list[dict[str, Any]] = []
        for item in section.get("items", []):
            code = item.get("code", "")
            hits = item.get("legal_hits") or []
            best = max((float(h.get("match_score") or 0) for h in hits), default=0.0)
            tier_info = classify_item_tier(
                item_code=code,
                priority=item.get("priority", "medium"),
                match_score=best,
                legal_hits=hits,
                grounded=code not in ungrounded,
                base_threshold=base_threshold,
                user_adjustment=int(adjustments.get(code, 0)),
            )
            if tier_info["tier"] == TIER_S1:
                s1 += 1
            elif tier_info["tier"] == TIER_S2:
                s2 += 1
            else:
                s3 += 1
                s3_codes.append(code)
            items_out.append({**item, **tier_info})
        tiered_sections.append({**section, "items": items_out})

    return {
        "sections": tiered_sections,
        "tier_summary": {
            "S1": s1,
            "S2": s2,
            "S3": s3,
            "s3_codes": s3_codes,
            "has_hard_block": s3 > 0,
        },
        "base_threshold": base_threshold,
        "tier_policy": "Legal-Skills 分层：S1 自动通过 · S2 人工复核 · S3 硬阻断",
    }
