"""End-to-end scenario pipelines for business submit and legal review prep."""

from __future__ import annotations

import copy
from typing import Any

from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.models.scenario import InvestigationScenario
from app.models.user import User
from app.schemas.scenario import BusinessSubmitRequest, ScenarioCreateRequest
from app.services.audit import write_audit_log
from app.services.brief_generator import generate_brief
from app.services.legal_ingest import ingest_corpus
from app.services.legal_rag import retrieve_for_checklist
from app.services.rule_engine import generate_checklist
from app.services.scenario_service import (
    _materials_only_payload,
    attach_document_extract_to_payload,
    business_submit_to_create_request,
    create_scenario_materials_only,
    create_scenario_with_checklist,
    regenerate_scenario_checklist,
    scenario_to_create_request,
)


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


def run_business_submit_materials(
    db: Session,
    user: User,
    payload: BusinessSubmitRequest,
) -> InvestigationScenario:
    """业务：上传/填写项目材料，提交法务确认协查范围（不生成清单）。"""
    return create_scenario_materials_only(db, user, payload)


def run_confirm_scope_and_generate(
    db: Session,
    user: User,
    scenario: InvestigationScenario,
    compliance_dimensions: list[str],
    *,
    polish: bool = False,
) -> InvestigationScenario:
    """法务：确认协查范围并生成清单、法源绑定与双语简报，进入待复核。"""
    if scenario.status != "pending_scope":
        raise ValueError("当前状态不可确认协查范围")

    old_payload = copy.deepcopy(scenario.checklist.payload if scenario.checklist else {})
    document_extract = old_payload.get("document_extract")
    revision_history = list(old_payload.get("revision_history") or [])
    revision_round = int(old_payload.get("revision_round") or 0)

    base = scenario_to_create_request(scenario)
    request = base.model_copy(update={"compliance_dimensions": compliance_dimensions})
    regenerate_scenario_checklist(db, scenario, request)

    checklist_payload = scenario.checklist.payload if scenario.checklist else {}
    if document_extract:
        checklist_payload = {**checklist_payload, "document_extract": document_extract}
    checklist_payload.pop("materials_only", None)

    if revision_history:
        checklist_payload["revision_history"] = revision_history
        checklist_payload["revision_round"] = revision_round

    scenario.checklist.payload = checklist_payload
    checklist_payload = _attach_legal_and_brief(scenario, checklist_payload, polish=polish)

    scenario.status = "pending_legal_review"
    scenario.compliance_dimensions = compliance_dimensions
    scenario.checklist.payload = copy.deepcopy(checklist_payload)
    flag_modified(scenario.checklist, "payload")
    db.commit()
    db.refresh(scenario)

    brief = checklist_payload.get("brief") or {}
    write_audit_log(
        db,
        user=user,
        action="scenario.confirm_scope",
        resource_type="scenario",
        resource_id=str(scenario.id),
        detail=(
            f"法务确认协查范围：{scenario.project_name}；"
            f"维度 {', '.join(compliance_dimensions)}；"
            f"通过 {brief.get('passed_count', 0)} 条，需复核 {brief.get('blocked_count', 0)} 条"
        ),
    )
    return scenario


def run_generate_and_submit(
    db: Session,
    user: User,
    payload: ScenarioCreateRequest,
    *,
    polish: bool = False,
) -> InvestigationScenario:
    """法务/演示：场景 → 清单 → 法源 → 简报 → 提交法务复核（保留兼容）。"""
    scenario = create_scenario_with_checklist(db, user, payload)
    checklist_payload = attach_document_extract_to_payload(scenario.checklist.payload, payload)
    scenario.checklist.payload = checklist_payload
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
            f"一键提交法务：{scenario.project_name}；"
            f"通过 {brief.get('passed_count', 0)} 条，需复核 {brief.get('blocked_count', 0)} 条"
        ),
    )
    return scenario


def run_revise_and_resubmit(
    db: Session,
    user: User,
    scenario: InvestigationScenario,
    payload: BusinessSubmitRequest,
) -> InvestigationScenario:
    """业务在同一项目补充材料后重新提交，待法务再次确认协查范围。"""
    if scenario.status != "returned_for_revision":
        raise ValueError("当前状态不可补充提交，请确认法务已退回该项目")

    old_payload = copy.deepcopy(scenario.checklist.payload if scenario.checklist else {})
    revision_history = list(old_payload.get("revision_history") or [])
    revision_round = len(revision_history) + 1
    revision_history.append(
        {
            "round": revision_round,
            "returned_at": old_payload.get("review", {}).get("returned_at"),
            "return_note": old_payload.get("review", {}).get("return_note"),
            "review": old_payload.get("review"),
            "description_snapshot": scenario.description,
            "compliance_dimensions": list(scenario.compliance_dimensions or []),
        }
    )

    create_req = business_submit_to_create_request(payload)
    scenario.project_name = create_req.project_name
    scenario.country = create_req.country
    scenario.state = create_req.state
    scenario.city = create_req.city
    scenario.industry = create_req.industry
    scenario.action_type = create_req.action_type
    scenario.investment_structure = create_req.investment_structure
    scenario.description = create_req.description
    scenario.employee_count = create_req.employee_count
    scenario.capacity_notes = create_req.capacity_notes
    scenario.facility_notes = create_req.facility_notes
    scenario.compliance_dimensions = []
    scenario.board_date = create_req.board_date
    scenario.start_date = create_req.start_date
    scenario.production_date = create_req.production_date
    scenario.remarks = create_req.remarks
    scenario.status = "pending_scope"

    materials_payload = _materials_only_payload(create_req)
    materials_payload = attach_document_extract_to_payload(materials_payload, create_req)
    materials_payload["revision_history"] = revision_history
    materials_payload["revision_round"] = len(revision_history)

    if not scenario.checklist:
        raise ValueError("场景缺少核查清单")

    scenario.checklist.title = materials_payload["title"]
    scenario.checklist.payload = materials_payload
    scenario.checklist.total_items = 0
    flag_modified(scenario.checklist, "payload")
    db.commit()
    db.refresh(scenario)

    write_audit_log(
        db,
        user=user,
        action="scenario.revise_and_resubmit",
        resource_type="scenario",
        resource_id=str(scenario.id),
        detail=(
            f"业务补充后重新提交材料（第 {len(revision_history) + 1} 轮）：{scenario.project_name}；"
            f"待法务确认协查范围"
        ),
    )
    return scenario


def scenario_summary_meta(status: str, checklist_payload: dict[str, Any] | None) -> dict[str, Any]:
    payload = checklist_payload or {}
    brief = payload.get("brief") or {}
    blocked = int(brief.get("blocked_count") or 0)
    passed = int(brief.get("passed_count") or 0)

    if status == "pending_scope":
        progress_status = "pending_scope"
    elif status == "pending_legal_review":
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
