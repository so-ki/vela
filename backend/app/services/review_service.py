from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from app.models.scenario import InvestigationScenario
from app.models.user import User


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _flatten_brief_items(brief: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for section in brief.get("sections", []):
        for item in section.get("items", []):
            items.append(
                {
                    **item,
                    "dimension_name": section.get("dimension_name", ""),
                }
            )
    return items


def init_review(scenario: InvestigationScenario, user: User) -> dict[str, Any]:
    payload = scenario.checklist.payload
    brief = payload.get("brief")
    if not brief:
        raise ValueError("请先生成双语简报")

    existing = payload.get("review")
    if existing and existing.get("items"):
        return existing

    review_items = []
    for item in _flatten_brief_items(brief):
        review_items.append(
            {
                "code": item["code"],
                "title": item["title"],
                "dimension_name": item.get("dimension_name", ""),
                "gate_status": item.get("gate_status", "unknown"),
                "match_score": float(item.get("match_score", 0)),
                "decision": "pending",
                "comment": None,
                "reviewed_at": None,
            }
        )

    return {
        "status": "in_progress",
        "reviewer_name": user.full_name,
        "reviewer_id": user.id,
        "started_at": _utcnow().isoformat(),
        "finalized_at": None,
        "items": review_items,
    }


def _counts(items: list[dict[str, Any]]) -> tuple[int, int, int]:
    approved = sum(1 for i in items if i.get("decision") == "approved")
    rejected = sum(1 for i in items if i.get("decision") == "rejected")
    pending = sum(1 for i in items if i.get("decision") not in ("approved", "rejected"))
    return approved, rejected, pending


def update_review_item(
    review: dict[str, Any],
    *,
    code: str,
    decision: str,
    comment: Optional[str],
) -> dict[str, Any]:
    if review.get("status") in ("approved", "rejected", "partial"):
        raise ValueError("复核已定稿，无法修改")

    if decision not in ("approved", "rejected", "pending"):
        raise ValueError("decision 须为 approved、rejected 或 pending")

    items = review.get("items", [])
    target = next((i for i in items if i["code"] == code), None)
    if target is None:
        raise ValueError(f"条目 {code} 不存在")

    target["decision"] = decision
    target["comment"] = comment.strip() if comment else None
    target["reviewed_at"] = _utcnow().isoformat() if decision != "pending" else None
    return review


def approve_all_pending(review: dict[str, Any]) -> dict[str, Any]:
    if review.get("status") in ("approved", "rejected", "partial"):
        raise ValueError("复核已定稿，无法修改")

    now = _utcnow().isoformat()
    for item in review.get("items", []):
        if item.get("decision") == "pending":
            item["decision"] = "approved"
            item["reviewed_at"] = now
    return review


def finalize_review(review: dict[str, Any]) -> dict[str, Any]:
    if review.get("status") in ("approved", "rejected", "partial"):
        return review

    items = review.get("items", [])
    approved, rejected, pending = _counts(items)
    if pending > 0:
        raise ValueError(f"仍有 {pending} 条未复核，请全部确认或驳回后再定稿")

    if rejected == 0:
        status = "approved"
    elif approved == 0:
        status = "rejected"
    else:
        status = "partial"

    review["status"] = status
    review["finalized_at"] = _utcnow().isoformat()
    review["approved_count"] = approved
    review["rejected_count"] = rejected
    review["pending_count"] = 0
    return review


def review_to_response(scenario_id: int, review: dict[str, Any]) -> dict[str, Any]:
    items = review.get("items", [])
    approved, rejected, pending = _counts(items)
    status = review.get("status", "in_progress")
    can_finalize = status == "in_progress" and pending == 0 and len(items) > 0
    can_export = status in ("approved", "partial", "rejected")

    return {
        "scenario_id": scenario_id,
        "status": status,
        "reviewer_name": review.get("reviewer_name", ""),
        "started_at": review.get("started_at"),
        "finalized_at": review.get("finalized_at"),
        "items": items,
        "approved_count": approved,
        "rejected_count": rejected,
        "pending_count": pending,
        "can_finalize": can_finalize,
        "can_export": can_export,
    }
