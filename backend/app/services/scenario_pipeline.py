"""End-to-end scenario pipelines for business submit and legal review prep."""

from __future__ import annotations

import copy
from typing import Any

from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.models.scenario import InvestigationScenario
from app.models.user import User
from app.schemas.scenario import ScenarioCreateRequest
from app.services.audit import write_audit_log
from app.services.brief_generator import generate_brief
from app.services.legal_ingest import ingest_corpus
from app.services.legal_rag import retrieve_for_checklist
from app.services.rule_engine import ScenarioInput, generate_checklist
from app.services.scenario_service import create_scenario_with_checklist, regenerate_scenario_checklist


def _attach_legal_and_brief(
    scenario: InvestigationScenario,
    payload: dict[str, Any],
    *,
    polish: bool,
) -> dict[str, Any]:
    ingest_corpus(force=False)
    result = retrieve_for_checklist(payload.get("sections", []))
    payload = {
        **payload,
        "sections_with_legal": result["sections"],
        "legal_retrieved": True,
    }
    scenario.checklist.payload = payload

    brief = generate_brief(
        scenario,
        payload,
        sections_with_legal=result["sections"],
        polish=polish,
    )
    payload = {**payload, "brief": brief}
    scenario.checklist.payload = payload
    scenario.status = "brief_generated" if brief["status"] != "blocked" else "brief_blocked"
    return payload


def run_generate_and_submit(
    db: Session,
    user: User,
    payload: ScenarioCreateRequest,
    *,
    polish: bool = False,
) -> InvestigationScenario:
    """业务一键：场景 → 清单 → 法源 → 简报 → 提交法务复核。"""
    scenario = create_scenario_with_checklist(db, user, payload)
    checklist_payload = scenario.checklist.payload
    checklist_payload = _attach_legal_and_brief(scenario, checklist_payload, polish=polish)

    scenario.status = "pending_legal_review"
    scenario.checklist.payload = copy.deepcopy(checklist_payload)
    flag_modified(scenario.checklist, "payload")
    db.commit()
    db.refresh(scenario)

    brief = checklist_payload.get("brief") or {}
    write_audit_log(
        db,
        user=user,
        action="scenario.generate_and_submit",
        resource_type="scenario",
        resource_id=str(scenario.id),
        detail=(
            f"业务一键提交法务：{scenario.project_name}；"
            f"通过 {brief.get('passed_count', 0)} 条，需复核 {brief.get('blocked_count', 0)} 条"
        ),
    )
    return scenario


def run_revise_and_resubmit(
    db: Session,
    user: User,
    scenario: InvestigationScenario,
    payload: ScenarioCreateRequest,
    *,
    polish: bool = False,
) -> InvestigationScenario:
    """业务在同一项目补充材料后重新生成清单/简报并提交法务。"""
    if scenario.status != "returned_for_revision":
        raise ValueError("当前状态不可补充提交，请确认法务已退回该项目")

    old_payload = copy.deepcopy(scenario.checklist.payload)
    revision_history = list(old_payload.get("revision_history") or [])
    revision_round = len(revision_history) + 1
    revision_history.append(
        {
            "round": revision_round,
            "returned_at": old_payload.get("review", {}).get("returned_at"),
            "return_note": old_payload.get("review", {}).get("return_note"),
            "review": old_payload.get("review"),
            "description_snapshot": scenario.description,
        }
    )

    regenerate_scenario_checklist(db, scenario, payload)
    checklist_payload = scenario.checklist.payload
    checklist_payload = _attach_legal_and_brief(scenario, checklist_payload, polish=polish)
    checklist_payload["revision_history"] = revision_history
    checklist_payload["revision_round"] = len(revision_history)
    checklist_payload.pop("review", None)

    scenario.status = "pending_legal_review"
    scenario.checklist.payload = copy.deepcopy(checklist_payload)
    scenario.checklist.total_items = checklist_payload["total_items"]
    flag_modified(scenario.checklist, "payload")
    db.commit()
    db.refresh(scenario)

    brief = checklist_payload.get("brief") or {}
    write_audit_log(
        db,
        user=user,
        action="scenario.revise_and_resubmit",
        resource_type="scenario",
        resource_id=str(scenario.id),
        detail=(
            f"业务补充后重新提交（第 {len(revision_history) + 1} 轮）：{scenario.project_name}；"
            f"通过 {brief.get('passed_count', 0)} 条，需复核 {brief.get('blocked_count', 0)} 条"
        ),
    )
    return scenario


def scenario_summary_meta(status: str, checklist_payload: dict[str, Any] | None) -> dict[str, Any]:
    payload = checklist_payload or {}
    brief = payload.get("brief") or {}
    blocked = int(brief.get("blocked_count") or 0)
    passed = int(brief.get("passed_count") or 0)

    if status == "pending_legal_review":
        progress_status = "submitted"
    elif status == "returned_for_revision":
        progress_status = "needs_revision"
    elif status == "review_in_progress":
        progress_status = "in_review"
    elif status.startswith("review_"):
        progress_status = "finalized"
    elif status in ("checklist_generated", "brief_generated", "brief_blocked"):
        progress_status = "processing"
    else:
        progress_status = "processing"

    needs_revision = status == "returned_for_revision"

    if status == "pending_legal_review" and blocked >= 3:
        review_priority = "high"
    elif blocked > 0 or status == "brief_blocked":
        review_priority = "medium"
    else:
        review_priority = "low"

    priority_order = {"high": 0, "medium": 1, "low": 2}

    return {
        "progress_status": progress_status,
        "review_priority": review_priority,
        "priority_order": priority_order.get(review_priority, 9),
        "blocked_count": blocked,
        "passed_count": passed,
        "needs_revision": needs_revision,
    }
