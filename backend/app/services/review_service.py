from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from app.services.investigation_adequacy_service import gate_a_blocking_review_message
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


def _legal_hits_by_code(payload: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    mapping: dict[str, list[dict[str, Any]]] = {}
    sections = payload.get("sections_with_legal") or payload.get("sections") or []
    for section in sections:
        for item in section.get("items", []):
            code = item.get("code")
            if code:
                mapping[code] = item.get("legal_hits") or []
    return mapping


def _assert_gate_a_allows_review(scenario: InvestigationScenario) -> None:
    if not scenario.checklist:
        return
    payload = scenario.checklist.payload or {}
    block = gate_a_blocking_review_message(payload.get("investigation_adequacy"))
    if block:
        raise ValueError(block)


def init_review(scenario: InvestigationScenario, user: User) -> dict[str, Any]:
    _assert_gate_a_allows_review(scenario)
    payload = scenario.checklist.payload
    brief = payload.get("brief")
    if not brief:
        raise ValueError("请先生成双语简报")

    existing = payload.get("review")
    if existing and existing.get("items"):
        return existing

    hits_by_code = _legal_hits_by_code(payload)
    review_items = []
    for item in _flatten_brief_items(brief):
        review_items.append(
            {
                "code": item["code"],
                "title": item["title"],
                "dimension_name": item.get("dimension_name", ""),
                "gate_status": item.get("gate_status", "unknown"),
                "match_score": float(item.get("match_score", 0)),
                "tier": item.get("tier", ""),
                "hard_block": bool(item.get("hard_block")),
                "decision": "pending",
                "comment": None,
                "external_counsel_required": False,
                "legal_hits": hits_by_code.get(item["code"], [])[:3],
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


def _s3_blocks_finalize(items: list[dict[str, Any]], tier_report: dict[str, Any] | None) -> bool:
    s3_codes = set((tier_report or {}).get("s3_codes") or [])
    if not s3_codes:
        return False
    return any(
        i.get("code") in s3_codes and i.get("decision") != "approved"
        for i in items
    )


def update_review_item(
    review: dict[str, Any],
    *,
    code: str,
    decision: str,
    comment: Optional[str],
    external_counsel_required: Optional[bool] = None,
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
    if external_counsel_required is not None:
        target["external_counsel_required"] = external_counsel_required
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


def finalize_review(
    review: dict[str, Any],
    *,
    revision_round: int = 0,
    finalize_seq: int = 0,
    tier_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if review.get("status") in ("approved", "rejected", "partial"):
        return review

    items = review.get("items", [])
    approved, rejected, pending = _counts(items)
    if pending > 0:
        raise ValueError(f"仍有 {pending} 条未复核，请全部确认或驳回后再定稿")

    s3_codes = set((tier_report or {}).get("s3_codes") or [])
    if s3_codes:
        unresolved = [
            i["code"]
            for i in items
            if i.get("code") in s3_codes and i.get("decision") != "approved"
        ]
        if unresolved:
            shown = ", ".join(unresolved[:6])
            extra = f" 等 {len(unresolved)} 条" if len(unresolved) > 6 else ""
            raise ValueError(
                f"S3 硬阻断条目须逐项「确认通过」后方可定稿：{shown}{extra}"
            )

    if rejected == 0:
        status = "approved"
    elif approved == 0:
        status = "rejected"
    else:
        status = "partial"

    major = 1 + revision_round
    review["version_label"] = f"v{major}.{finalize_seq}"
    review["status"] = status
    review["finalized_at"] = _utcnow().isoformat()
    review["approved_count"] = approved
    review["rejected_count"] = rejected
    review["pending_count"] = 0
    return review


def review_to_response(scenario_id: int, review: dict[str, Any], *, tier_report: dict[str, Any] | None = None) -> dict[str, Any]:
    tier_report = tier_report or review.get("tier_report")
    items = review.get("items", [])
    approved, rejected, pending = _counts(items)
    status = review.get("status", "in_progress")
    can_finalize = (
        status == "in_progress"
        and pending == 0
        and len(items) > 0
        and not _s3_blocks_finalize(items, tier_report)
    )
    can_export = status in ("approved", "partial", "rejected") and not _s3_blocks_finalize(items, tier_report)
    can_return = status == "in_progress" and rejected > 0
    s3_blocked = _s3_blocks_finalize(items, tier_report)

    return {
        "scenario_id": scenario_id,
        "status": status,
        "reviewer_name": review.get("reviewer_name", ""),
        "started_at": review.get("started_at"),
        "finalized_at": review.get("finalized_at"),
        "version_label": review.get("version_label"),
        "items": items,
        "approved_count": approved,
        "rejected_count": rejected,
        "pending_count": pending,
        "can_finalize": can_finalize,
        "can_export": can_export,
        "can_return_to_business": can_return,
        "s3_finalize_blocked": s3_blocked,
    }


def return_review_to_business(
    review: dict[str, Any],
    user: User,
    *,
    note: Optional[str] = None,
) -> dict[str, Any]:
    """法务将含驳回条目的复核退回业务补充（同一项目）。"""
    if review.get("status") != "in_progress":
        raise ValueError("仅「复核进行中」可退回业务补充")

    approved, rejected, pending = _counts(review.get("items", []))
    if rejected == 0:
        raise ValueError("须至少有一条「已驳回」条目方可退回业务")

    rejected_items = [
        {
            "code": i.get("code"),
            "title": i.get("title"),
            "comment": i.get("comment"),
            "external_counsel_required": i.get("external_counsel_required"),
        }
        for i in review.get("items", [])
        if i.get("decision") == "rejected"
    ]

    review["status"] = "returned"
    review["returned_at"] = _utcnow().isoformat()
    review["returned_by"] = user.full_name
    review["returned_by_id"] = user.id
    review["return_note"] = note.strip() if note else None
    review["return_snapshot"] = {
        "approved_count": approved,
        "rejected_count": rejected,
        "pending_count": pending,
        "rejected_items": rejected_items,
    }
    return review


def business_feedback_from_review(review: dict[str, Any] | None) -> dict[str, Any] | None:
    """面向业务提交人的复核摘要：仅含驳回批注与需外聘标记，不含完整法条片段。"""
    if not review or not review.get("items"):
        return None

    items = review.get("items", [])
    approved, rejected, pending = _counts(items)
    status = review.get("status", "in_progress")

    feedback_items: list[dict[str, Any]] = []
    for item in items:
        decision = item.get("decision")
        external = bool(item.get("external_counsel_required"))
        comment = (item.get("comment") or "").strip()
        if decision == "rejected" or external:
            feedback_items.append(
                {
                    "code": item.get("code"),
                    "title": item.get("title"),
                    "dimension_name": item.get("dimension_name", ""),
                    "decision": decision,
                    "comment": comment or None,
                    "external_counsel_required": external,
                    "reviewed_at": item.get("reviewed_at"),
                }
            )

    if not feedback_items and status == "in_progress" and pending == len(items):
        return {
            "review_status": status,
            "is_finalized": False,
            "is_returned": False,
            "approved_count": approved,
            "rejected_count": rejected,
            "pending_count": pending,
            "action_required": False,
            "summary": "法务已开始复核，暂无需要您处理的反馈。",
            "items": [],
        }

    action_required = rejected > 0 or any(i.get("external_counsel_required") for i in feedback_items)
    is_finalized = status in ("approved", "partial", "rejected")
    is_returned = status == "returned"

    if is_returned:
        summary = (
            f"法务已退回补充：{rejected} 条驳回须处理。"
            + (f" 说明：{review.get('return_note')}" if review.get("return_note") else "")
            + " 请在本项目补充材料后重新提交。"
        )
    elif is_finalized:
        if rejected > 0:
            summary = f"法务已定稿：{rejected} 条协查结论被驳回，请根据批注补充材料。"
        elif any(i.get("external_counsel_required") for i in feedback_items):
            summary = "法务已定稿：部分条目标记需外聘巴西律所，请按批注安排。"
        else:
            summary = "法务已定稿，协查流程已完成。"
    elif rejected > 0 or feedback_items:
        summary = f"法务复核中：{rejected} 条已驳回，请查看批注并与法务沟通。"
    else:
        summary = "法务复核中，暂无需要您处理的反馈。"

    return {
        "review_status": status,
        "is_finalized": is_finalized,
        "is_returned": is_returned,
        "approved_count": approved,
        "rejected_count": rejected,
        "pending_count": pending,
        "action_required": action_required or is_returned,
        "summary": summary,
        "items": feedback_items,
        "return_note": review.get("return_note"),
    }
