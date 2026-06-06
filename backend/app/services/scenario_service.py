from __future__ import annotations

from sqlalchemy.orm import Session, joinedload

from app.models.scenario import ComplianceChecklist, InvestigationScenario, utcnow
from app.models.user import User
from app.schemas.scenario import (
    BusinessSubmitRequest,
    ChecklistResponse,
    DocumentExtractSnapshot,
    MaterialFeedback,
    ScenarioCreateRequest,
    ScenarioResponse,
    BusinessFeedback,
)
from app.services.audit import write_audit_log
from app.services.review_service import business_feedback_from_review
from app.services.material_review_service import (
    assess_material_completeness,
    build_material_return_record,
    business_feedback_from_material_review,
)
from app.services.rule_engine import (
    ScenarioInput,
    generate_checklist,
    get_demo_scenario_template,
    get_material_field_labels,
    load_rules,
)
from app.services.rules_registry import resolve_pack_id, resolve_scenario_pack_id
from app.services.material_file_storage import save_scenario_material_files


def _pack_labels(action_type: str, pack_id: str | None = None) -> tuple[str, str]:
    rules = load_rules(pack_id)
    pack = rules.get("pack", {})
    action = rules.get("action_types", {}).get(action_type, {})
    return (
        pack.get("name") or "巴西 · 投资协查",
        action.get("name") or action_type,
    )


def _resolve_payload_pack_id(payload: BusinessSubmitRequest | ScenarioCreateRequest) -> str:
    return resolve_pack_id(getattr(payload, "rules_pack_id", None), payload.country)


def _materials_only_payload(
    payload: BusinessSubmitRequest | ScenarioCreateRequest,
    *,
    document_extract: dict | None = None,
) -> dict:
    """业务材料占位清单：不含核查项，待法务确认协查范围。"""
    pack_id = _resolve_payload_pack_id(payload)
    pack_name, action_name = _pack_labels(payload.action_type, pack_id)
    rules = load_rules(pack_id)
    industry_name = rules.get("industries", {}).get(payload.industry, {}).get("name", payload.industry)
    data: dict = {
        "title": "待法务确认协查范围",
        "total_items": 0,
        "jurisdiction": rules["jurisdiction"]["name"],
        "industry_pack_id": pack_id,
        "industry_pack_name": pack_name,
        "detected_industry": payload.industry,
        "detected_industry_name": industry_name,
        "detected_sub_sectors": [],
        "detected_action_type": payload.action_type,
        "detected_action_type_name": action_name,
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
    *,
    uploads: list[tuple[str, bytes, str | None]] | None = None,
) -> InvestigationScenario:
    """业务提交材料：保存场景与抽取记录，不生成核查清单。"""
    pack_id = _resolve_payload_pack_id(payload)
    checklist_payload = _materials_only_payload(payload)
    if payload.document_extract:
        checklist_payload = attach_document_extract_to_payload(checklist_payload, payload)

    scenario = InvestigationScenario(
        user_id=user.id,
        project_name=payload.project_name,
        rules_pack_id=pack_id,
        country=payload.country,
        state=payload.state,
        city=payload.city,
        industry=payload.industry,
        action_type=payload.action_type,
        investment_structure=payload.investment_structure,
        investment_destination=payload.investment_destination,
        project_content_scale=payload.project_content_scale,
        funding_source=payload.funding_source,
        description=payload.description,
        known_risks=payload.known_risks,
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

    if uploads:
        archived_files = save_scenario_material_files(scenario.id, uploads)
        doc = dict(checklist_payload.get("document_extract") or {})
        doc["archived_files"] = archived_files
        checklist_payload["document_extract"] = doc

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
    pack_id = resolve_scenario_pack_id(
        rules_pack_id=scenario.rules_pack_id,
        country=scenario.country,
        checklist_payload=scenario.checklist.payload if scenario.checklist else None,
    )
    return ScenarioCreateRequest(
        project_name=scenario.project_name,
        rules_pack_id=pack_id,
        country=scenario.country,
        state=scenario.state,
        city=scenario.city,
        industry=scenario.industry,
        action_type=scenario.action_type,
        investment_structure=scenario.investment_structure,
        investment_destination=scenario.investment_destination,
        project_content_scale=scenario.project_content_scale,
        funding_source=scenario.funding_source,
        description=scenario.description,
        known_risks=scenario.known_risks,
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
    pack_id = _resolve_payload_pack_id(payload)
    scenario_input = ScenarioInput(
        project_name=payload.project_name,
        country=payload.country,
        state=payload.state,
        city=payload.city,
        industry=payload.industry,
        action_type=payload.action_type,
        investment_structure=payload.investment_structure or "",
        investment_destination=payload.investment_destination or "",
        project_content_scale=payload.project_content_scale or "",
        funding_source=payload.funding_source or "",
        description=payload.description,
        known_risks=payload.known_risks or "",
        compliance_dimensions=payload.compliance_dimensions,
        employee_count=payload.employee_count,
        capacity_notes=payload.capacity_notes,
        facility_notes=payload.facility_notes,
        board_date=str(payload.board_date) if payload.board_date else None,
        start_date=str(payload.start_date) if payload.start_date else None,
        production_date=str(payload.production_date) if payload.production_date else None,
        remarks=payload.remarks,
        rules_pack_id=pack_id,
    )

    checklist_data = generate_checklist(scenario_input, pack_id)

    scenario = InvestigationScenario(
        user_id=user.id,
        project_name=payload.project_name,
        rules_pack_id=pack_id,
        country=payload.country,
        state=payload.state,
        city=payload.city,
        industry=payload.industry,
        action_type=payload.action_type,
        investment_structure=payload.investment_structure,
        investment_destination=payload.investment_destination,
        project_content_scale=payload.project_content_scale,
        funding_source=payload.funding_source,
        description=payload.description,
        known_risks=payload.known_risks,
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
    pack_id = _resolve_payload_pack_id(payload)
    return ScenarioInput(
        project_name=payload.project_name,
        country=payload.country,
        state=payload.state,
        city=payload.city,
        industry=payload.industry,
        action_type=payload.action_type,
        investment_structure=payload.investment_structure or "",
        investment_destination=payload.investment_destination or "",
        project_content_scale=payload.project_content_scale or "",
        funding_source=payload.funding_source or "",
        description=payload.description,
        known_risks=payload.known_risks or "",
        compliance_dimensions=payload.compliance_dimensions,
        employee_count=payload.employee_count,
        capacity_notes=payload.capacity_notes,
        facility_notes=payload.facility_notes,
        board_date=str(payload.board_date) if payload.board_date else None,
        start_date=str(payload.start_date) if payload.start_date else None,
        production_date=str(payload.production_date) if payload.production_date else None,
        remarks=payload.remarks,
        rules_pack_id=pack_id,
    )


def _apply_payload_to_scenario(scenario: InvestigationScenario, payload: ScenarioCreateRequest) -> None:
    scenario.project_name = payload.project_name
    scenario.rules_pack_id = _resolve_payload_pack_id(payload)
    scenario.country = payload.country
    scenario.state = payload.state
    scenario.city = payload.city
    scenario.industry = payload.industry
    scenario.action_type = payload.action_type
    scenario.investment_structure = payload.investment_structure
    scenario.investment_destination = payload.investment_destination
    scenario.project_content_scale = payload.project_content_scale
    scenario.funding_source = payload.funding_source
    scenario.description = payload.description
    scenario.known_risks = payload.known_risks
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
    pack_id = _resolve_payload_pack_id(payload)
    checklist_data = generate_checklist(_payload_from_request(payload), pack_id)

    if not scenario.checklist:
        raise ValueError("场景缺少核查清单")

    scenario.checklist.title = checklist_data["title"]
    scenario.checklist.payload = checklist_data
    scenario.checklist.total_items = checklist_data["total_items"]
    scenario.status = "checklist_generated"
    db.flush()
    return checklist_data


def _material_feedback_resp(scenario: InvestigationScenario) -> MaterialFeedback | None:
    if not scenario.checklist:
        return None
    raw = business_feedback_from_material_review(
        (scenario.checklist.payload or {}).get("material_review")
    )
    if raw is None:
        return None
    return MaterialFeedback(**raw)


def scenario_to_response(scenario: InvestigationScenario) -> ScenarioResponse:
    checklist_resp = None
    checklist_payload = scenario.checklist.payload if scenario.checklist else {}
    resolved_pack_id = resolve_scenario_pack_id(
        rules_pack_id=scenario.rules_pack_id,
        country=scenario.country,
        checklist_payload=checklist_payload or None,
    )
    if scenario.checklist:
        payload = checklist_payload
        checklist_resp = ChecklistResponse(
            id=scenario.checklist.id,
            title=payload["title"],
            version=scenario.checklist.version,
            total_items=payload["total_items"],
            jurisdiction=payload["jurisdiction"],
            industry_pack_id=payload.get("industry_pack_id") or resolved_pack_id,
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

    payload = checklist_payload
    revision_round = int(payload.get("revision_round") or 0)
    material_review = payload.get("material_review") or {}

    return ScenarioResponse(
        id=scenario.id,
        project_name=scenario.project_name,
        rules_pack_id=resolved_pack_id,
        country=scenario.country,
        state=scenario.state,
        city=scenario.city,
        industry=scenario.industry,
        action_type=scenario.action_type,
        investment_structure=scenario.investment_structure,
        investment_destination=scenario.investment_destination,
        project_content_scale=scenario.project_content_scale,
        funding_source=scenario.funding_source,
        description=scenario.description,
        known_risks=scenario.known_risks,
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
        material_feedback=_material_feedback_resp(scenario),
        material_scope_dimensions=list(material_review.get("selected_dimensions") or []),
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
        investment_destination=scenario.investment_destination,
        project_content_scale=scenario.project_content_scale,
        funding_source=scenario.funding_source,
        description=scenario.description,
        known_risks=scenario.known_risks,
        employee_count=scenario.employee_count,
        capacity_notes=scenario.capacity_notes,
        facility_notes=scenario.facility_notes,
        remarks=scenario.remarks,
        compliance_dimensions=scenario.compliance_dimensions or [],
        facts=facts,
        disclaimer="本项目提交时未保存上传抽取记录；下表由当前表单字段还原，供业务核对。",
    )
