from __future__ import annotations

from sqlalchemy.orm import Session, joinedload

from app.models.scenario import ComplianceChecklist, InvestigationScenario, utcnow
from app.models.user import User
from app.schemas.scenario import (
    BusinessSubmitRequest,
    ChecklistResponse,
    DocumentExtractSnapshot,
    ScenarioCreateRequest,
    ScenarioResponse,
    BusinessFeedback,
)
from app.services.audit import write_audit_log
from app.services.review_service import business_feedback_from_review
from app.services.rule_engine import ScenarioInput, generate_checklist, get_demo_scenario_template


def _materials_only_payload(
    payload: BusinessSubmitRequest | ScenarioCreateRequest,
    *,
    document_extract: dict | None = None,
) -> dict:
    """业务材料占位清单：不含核查项，待法务确认协查范围。"""
    data: dict = {
        "title": "待法务确认协查范围",
        "total_items": 0,
        "jurisdiction": "Brazil",
        "industry_pack_name": "巴西 · 新能源（专包 v2）",
        "detected_industry": payload.industry,
        "detected_industry_name": "新能源",
        "detected_sub_sectors": [],
        "detected_action_type": payload.action_type,
        "detected_action_type_name": "境外设厂",
        "selected_dimensions": [],
        "sections": [],
        "materials_only": True,
        "disclaimer": (
            "业务已提交项目材料。协查范围与核查清单将由法务确认合规维度后生成，"
            "本阶段不构成法律意见。"
        ),
    }
    if document_extract:
        data["document_extract"] = document_extract
    return data


def create_scenario_materials_only(
    db: Session,
    user: User,
    payload: BusinessSubmitRequest,
) -> InvestigationScenario:
    """业务提交材料：保存场景与抽取记录，不生成核查清单。"""
    checklist_payload = _materials_only_payload(payload)
    if payload.document_extract:
        checklist_payload = attach_document_extract_to_payload(checklist_payload, payload)

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
        compliance_dimensions=[],
        board_date=payload.board_date,
        start_date=payload.start_date,
        production_date=payload.production_date,
        remarks=payload.remarks,
        status="pending_scope",
    )
    db.add(scenario)
    db.flush()

    checklist = ComplianceChecklist(
        scenario_id=scenario.id,
        title=checklist_payload["title"],
        version="v0.1",
        payload=checklist_payload,
        total_items=0,
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
        action="scenario.submit_materials",
        resource_type="scenario",
        resource_id=str(loaded.id),
        detail=f"业务提交项目材料：{payload.project_name}（待法务确认协查范围）",
    )
    return loaded


def business_submit_to_create_request(payload: BusinessSubmitRequest) -> ScenarioCreateRequest:
    return ScenarioCreateRequest(**payload.model_dump(), compliance_dimensions=[])


def scenario_to_create_request(scenario: InvestigationScenario) -> ScenarioCreateRequest:
    return ScenarioCreateRequest(
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
        compliance_dimensions=list(scenario.compliance_dimensions or []),
        board_date=scenario.board_date,
        start_date=scenario.start_date,
        production_date=scenario.production_date,
        remarks=scenario.remarks,
    )


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
        document_extract=document_extract_for_scenario(scenario),
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


def attach_document_extract_to_payload(
    payload: dict,
    request: BusinessSubmitRequest | ScenarioCreateRequest,
) -> dict:
    if not request.document_extract:
        return payload
    snap = request.document_extract.model_copy(
        update={
            "extracted_at": request.document_extract.extracted_at or utcnow(),
            "source": request.document_extract.source or "upload",
        }
    )
    return {**payload, "document_extract": snap.model_dump(mode="json")}


def document_extract_for_scenario(
    scenario: InvestigationScenario,
) -> DocumentExtractSnapshot | None:
    if not scenario.checklist:
        return None
    payload = scenario.checklist.payload or {}
    raw = payload.get("document_extract")
    if raw:
        return DocumentExtractSnapshot(**raw)

    facts = []
    if scenario.project_name:
        facts.append({"field": "project_name", "value": scenario.project_name, "source_snippet": None})
    if scenario.investment_structure:
        facts.append(
            {
                "field": "investment_structure",
                "value": scenario.investment_structure,
                "source_snippet": None,
            }
        )
    if scenario.employee_count:
        facts.append(
            {
                "field": "employee_count",
                "value": str(scenario.employee_count),
                "source_snippet": None,
            }
        )
    if scenario.description:
        facts.append(
            {
                "field": "description",
                "value": scenario.description[:200],
                "source_snippet": None,
            }
        )

    return DocumentExtractSnapshot(
        filename="（未保留上传方案）",
        mode="manual",
        source="manual",
        extracted_at=scenario.created_at,
        project_name=scenario.project_name,
        investment_structure=scenario.investment_structure,
        description=scenario.description,
        employee_count=scenario.employee_count,
        capacity_notes=scenario.capacity_notes,
        facility_notes=scenario.facility_notes,
        remarks=scenario.remarks,
        compliance_dimensions=scenario.compliance_dimensions or [],
        facts=facts,
        disclaimer="本项目提交时未保存上传抽取记录；下表由当前表单字段还原，供业务核对。",
    )
