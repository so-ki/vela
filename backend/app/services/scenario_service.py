from __future__ import annotations

from sqlalchemy.orm import Session, joinedload

from app.models.scenario import ComplianceChecklist, InvestigationScenario
from app.models.user import User
from app.schemas.scenario import ChecklistResponse, ScenarioCreateRequest, ScenarioResponse, BusinessFeedback
from app.services.audit import write_audit_log
from app.services.review_service import business_feedback_from_review
from app.services.rule_engine import ScenarioInput, generate_checklist, get_demo_scenario_template


def create_scenario_with_checklist(
    db: Session,
    user: User,
    payload: ScenarioCreateRequest,
) -> InvestigationScenario:
    scenario_input = ScenarioInput(
        project_name=payload.project_name,
        country=payload.country,
        state=payload.state,
        city=payload.city,
        industry=payload.industry,
        action_type=payload.action_type,
        investment_structure=payload.investment_structure or "",
        description=payload.description,
        compliance_dimensions=payload.compliance_dimensions,
        employee_count=payload.employee_count,
        capacity_notes=payload.capacity_notes,
        facility_notes=payload.facility_notes,
        board_date=str(payload.board_date) if payload.board_date else None,
        start_date=str(payload.start_date) if payload.start_date else None,
        production_date=str(payload.production_date) if payload.production_date else None,
        remarks=payload.remarks,
    )

    checklist_data = generate_checklist(scenario_input)

    scenario = InvestigationScenario(
        user_id=user.id,
        project_name=payload.project_name,
        country=payload.country,
        state=payload.state,
        city=payload.city,
        industry=payload.industry,
        action_type=payload.action_type,
        investment_structure=payload.investment_structure,
        description=payload.description,
        employee_count=payload.employee_count,
        capacity_notes=payload.capacity_notes,
        facility_notes=payload.facility_notes,
        compliance_dimensions=payload.compliance_dimensions,
        board_date=payload.board_date,
        start_date=payload.start_date,
        production_date=payload.production_date,
        remarks=payload.remarks,
        status="checklist_generated",
    )
    db.add(scenario)
    db.flush()

    checklist = ComplianceChecklist(
        scenario_id=scenario.id,
        title=checklist_data["title"],
        version="v0.1",
        payload=checklist_data,
        total_items=checklist_data["total_items"],
    )
    db.add(checklist)
    db.commit()

    loaded = (
        db.query(InvestigationScenario)
        .options(joinedload(InvestigationScenario.checklist))
        .filter(InvestigationScenario.id == scenario.id)
        .first()
    )
    assert loaded is not None

    write_audit_log(
        db,
        user=user,
        action="scenario.create",
        resource_type="scenario",
        resource_id=str(loaded.id),
        detail=f"生成核查清单 {checklist_data['total_items']} 条",
    )
    return loaded


def _payload_from_request(payload: ScenarioCreateRequest) -> ScenarioInput:
    return ScenarioInput(
        project_name=payload.project_name,
        country=payload.country,
        state=payload.state,
        city=payload.city,
        industry=payload.industry,
        action_type=payload.action_type,
        investment_structure=payload.investment_structure or "",
        description=payload.description,
        compliance_dimensions=payload.compliance_dimensions,
        employee_count=payload.employee_count,
        capacity_notes=payload.capacity_notes,
        facility_notes=payload.facility_notes,
        board_date=str(payload.board_date) if payload.board_date else None,
        start_date=str(payload.start_date) if payload.start_date else None,
        production_date=str(payload.production_date) if payload.production_date else None,
        remarks=payload.remarks,
    )


def _apply_payload_to_scenario(scenario: InvestigationScenario, payload: ScenarioCreateRequest) -> None:
    scenario.project_name = payload.project_name
    scenario.country = payload.country
    scenario.state = payload.state
    scenario.city = payload.city
    scenario.industry = payload.industry
    scenario.action_type = payload.action_type
    scenario.investment_structure = payload.investment_structure
    scenario.description = payload.description
    scenario.employee_count = payload.employee_count
    scenario.capacity_notes = payload.capacity_notes
    scenario.facility_notes = payload.facility_notes
    scenario.compliance_dimensions = payload.compliance_dimensions
    scenario.board_date = payload.board_date
    scenario.start_date = payload.start_date
    scenario.production_date = payload.production_date
    scenario.remarks = payload.remarks


def regenerate_scenario_checklist(
    db: Session,
    scenario: InvestigationScenario,
    payload: ScenarioCreateRequest,
) -> dict:
    """在同一 scenario 上重新生成清单（保留 revision_history 由调用方处理）。"""
    _apply_payload_to_scenario(scenario, payload)
    checklist_data = generate_checklist(_payload_from_request(payload))

    if not scenario.checklist:
        raise ValueError("场景缺少核查清单")

    scenario.checklist.title = checklist_data["title"]
    scenario.checklist.payload = checklist_data
    scenario.checklist.total_items = checklist_data["total_items"]
    scenario.status = "checklist_generated"
    db.flush()
    return checklist_data


def scenario_to_response(scenario: InvestigationScenario) -> ScenarioResponse:
    checklist_resp = None
    if scenario.checklist:
        payload = scenario.checklist.payload
        checklist_resp = ChecklistResponse(
            id=scenario.checklist.id,
            title=payload["title"],
            version=scenario.checklist.version,
            total_items=payload["total_items"],
            jurisdiction=payload["jurisdiction"],
            industry_pack_name=payload.get("industry_pack_name"),
            detected_industry=payload["detected_industry"],
            detected_industry_name=payload["detected_industry_name"],
            detected_sub_sectors=payload.get("detected_sub_sectors", []),
            detected_action_type=payload["detected_action_type"],
            detected_action_type_name=payload["detected_action_type_name"],
            selected_dimensions=payload["selected_dimensions"],
            sections=payload["sections"],
            disclaimer=payload["disclaimer"],
            created_at=scenario.checklist.created_at,
        )

    payload = scenario.checklist.payload if scenario.checklist else {}
    revision_round = int(payload.get("revision_round") or 0)

    return ScenarioResponse(
        id=scenario.id,
        project_name=scenario.project_name,
        country=scenario.country,
        state=scenario.state,
        city=scenario.city,
        industry=scenario.industry,
        action_type=scenario.action_type,
        investment_structure=scenario.investment_structure,
        description=scenario.description,
        employee_count=scenario.employee_count,
        capacity_notes=scenario.capacity_notes,
        facility_notes=scenario.facility_notes,
        compliance_dimensions=scenario.compliance_dimensions,
        board_date=scenario.board_date,
        start_date=scenario.start_date,
        production_date=scenario.production_date,
        remarks=scenario.remarks,
        status=scenario.status,
        created_at=scenario.created_at,
        checklist=checklist_resp,
        business_feedback=_business_feedback_resp(scenario),
        can_revise=scenario.status == "returned_for_revision",
        revision_round=revision_round,
    )


def _business_feedback_resp(scenario: InvestigationScenario) -> BusinessFeedback | None:
    if not scenario.checklist:
        return None
    raw = business_feedback_from_review(scenario.checklist.payload.get("review"))
    if raw is None:
        return None
    return BusinessFeedback(**raw)


def get_demo_request() -> ScenarioCreateRequest:
    return ScenarioCreateRequest(**get_demo_scenario_template())
