from typing import List
import copy
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.orm.attributes import flag_modified

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.scenario import InvestigationScenario
from app.models.user import User
from app.schemas.scenario import (
    RulesCatalogResponse,
    ScenarioCreateRequest,
    ScenarioResponse,
    ScenarioSummary,
)
from app.schemas.brief import BriefGenerateResponse
from app.schemas.legal import LegalRetrievalResponse
from app.schemas.review import ReviewItemUpdateRequest, ReviewResponse
from app.services.audit import write_audit_log
from app.services.brief_generator import generate_brief
from app.services.export_service import build_sample_docx
from app.services.legal_ingest import get_index_status, ingest_corpus
from app.services.legal_rag import retrieve_for_checklist
from app.services.review_service import (
    approve_all_pending,
    finalize_review,
    init_review,
    review_to_response,
    update_review_item,
)
from app.services.rule_engine import get_demo_scenario_template, get_rules_catalog
from app.services.scenario_service import create_scenario_with_checklist, get_demo_request, scenario_to_response

router = APIRouter(tags=["协查场景"])


def _save_payload(db: Session, scenario: InvestigationScenario, payload: dict) -> None:
    scenario.checklist.payload = copy.deepcopy(payload)
    flag_modified(scenario.checklist, "payload")
    db.commit()


@router.get("/rules/catalog", response_model=RulesCatalogResponse)
def rules_catalog(_: User = Depends(get_current_user)):
    return get_rules_catalog()


@router.get("/rules/demo-template")
def demo_template(_: User = Depends(get_current_user)):
    return get_demo_scenario_template()


@router.post("/scenarios", response_model=ScenarioResponse, status_code=201)
def create_scenario(
    payload: ScenarioCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    scenario = create_scenario_with_checklist(db, current_user, payload)
    return scenario_to_response(scenario)


@router.get("/scenarios", response_model=List[ScenarioSummary])
def list_scenarios(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rows = (
        db.query(InvestigationScenario)
        .options(joinedload(InvestigationScenario.checklist))
        .filter(InvestigationScenario.user_id == current_user.id)
        .order_by(InvestigationScenario.created_at.desc())
        .all()
    )
    return [
        ScenarioSummary(
            id=s.id,
            project_name=s.project_name,
            city=s.city,
            industry=s.industry,
            status=s.status,
            total_items=s.checklist.total_items if s.checklist else None,
            created_at=s.created_at,
        )
        for s in rows
    ]


@router.get("/scenarios/{scenario_id}", response_model=ScenarioResponse)
def get_scenario(
    scenario_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    scenario = (
        db.query(InvestigationScenario)
        .options(joinedload(InvestigationScenario.checklist))
        .filter(
            InvestigationScenario.id == scenario_id,
            InvestigationScenario.user_id == current_user.id,
        )
        .first()
    )
    if scenario is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="场景不存在")
    return scenario_to_response(scenario)


@router.post("/scenarios/demo/byd-campinas", response_model=ScenarioResponse, status_code=201)
def create_demo_scenario(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    payload = get_demo_request()
    scenario = create_scenario_with_checklist(db, current_user, payload)
    return scenario_to_response(scenario)


@router.post("/scenarios/{scenario_id}/retrieve", response_model=LegalRetrievalResponse)
def retrieve_legal_sources(
    scenario_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    scenario = (
        db.query(InvestigationScenario)
        .options(joinedload(InvestigationScenario.checklist))
        .filter(
            InvestigationScenario.id == scenario_id,
            InvestigationScenario.user_id == current_user.id,
        )
        .first()
    )
    if scenario is None or scenario.checklist is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="场景或清单不存在")

    ingest_corpus(force=False)
    payload = scenario.checklist.payload
    result = retrieve_for_checklist(payload.get("sections", []))

    scenario.checklist.payload = {
        **payload,
        "sections_with_legal": result["sections"],
        "legal_retrieved": True,
    }
    flag_modified(scenario.checklist, "payload")
    db.commit()

    return LegalRetrievalResponse(
        scenario_id=scenario_id,
        total_hits=result["total_hits"],
        zero_hit_items=result["zero_hit_items"],
        sections=result["sections"],
        disclaimer=result["disclaimer"],
        index_status=get_index_status(),
    )


def _load_owned_scenario(db: Session, scenario_id: int, user_id: int) -> InvestigationScenario:
    scenario = (
        db.query(InvestigationScenario)
        .options(joinedload(InvestigationScenario.checklist))
        .filter(
            InvestigationScenario.id == scenario_id,
            InvestigationScenario.user_id == user_id,
        )
        .first()
    )
    if scenario is None or scenario.checklist is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="场景或清单不存在")
    return scenario


@router.get("/scenarios/{scenario_id}/brief", response_model=BriefGenerateResponse)
def get_brief(
    scenario_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    scenario = _load_owned_scenario(db, scenario_id, current_user.id)
    brief = scenario.checklist.payload.get("brief")
    if not brief:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="尚未生成双语简报，请先调用生成接口")
    return BriefGenerateResponse(**brief)


@router.post("/scenarios/{scenario_id}/brief", response_model=BriefGenerateResponse)
def create_brief(
    scenario_id: int,
    polish: bool = Query(default=True, description="启用 LLM 润色（需配置 API Key）"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    scenario = _load_owned_scenario(db, scenario_id, current_user.id)
    payload = scenario.checklist.payload

    if not payload.get("legal_retrieved"):
        ingest_corpus(force=False)
        result = retrieve_for_checklist(payload.get("sections", []))
        payload = {
            **payload,
            "sections_with_legal": result["sections"],
            "legal_retrieved": True,
        }
        scenario.checklist.payload = payload

    try:
        brief = generate_brief(
            scenario,
            payload,
            sections_with_legal=payload.get("sections_with_legal"),
            polish=polish,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    payload = copy.deepcopy(scenario.checklist.payload)
    payload = {**payload, "brief": brief}
    scenario.status = "brief_generated" if brief["status"] != "blocked" else "brief_blocked"
    _save_payload(db, scenario, payload)

    write_audit_log(
        db,
        user=current_user,
        action="brief.generate",
        resource_type="scenario",
        resource_id=str(scenario.id),
        detail=f"生成双语简报：通过 {brief['passed_count']} 条，需复核 {brief['blocked_count']} 条（模式 {brief.get('mode', 'template')}）",
    )

    return BriefGenerateResponse(**brief)


def _ensure_brief(scenario: InvestigationScenario, payload: dict) -> dict:
    if payload.get("brief"):
        return payload
    if not payload.get("legal_retrieved"):
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
        sections_with_legal=payload.get("sections_with_legal"),
        polish=False,
    )
    payload = {**payload, "brief": brief}
    scenario.checklist.payload = payload
    scenario.status = "brief_generated" if brief["status"] != "blocked" else "brief_blocked"
    return payload


@router.post("/scenarios/demo/sample", response_model=ScenarioResponse, status_code=201)
def create_full_sample(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """一键生成完整样本：演示场景 → 法源绑定 → 双语简报 → 初始化复核。"""
    scenario = create_scenario_with_checklist(db, current_user, get_demo_request())
    payload = scenario.checklist.payload

    ingest_corpus(force=False)
    result = retrieve_for_checklist(payload.get("sections", []))
    payload = {
        **payload,
        "sections_with_legal": result["sections"],
        "legal_retrieved": True,
    }
    scenario.checklist.payload = payload

    brief = generate_brief(
        scenario, payload, sections_with_legal=result["sections"], polish=True
    )
    payload = {**payload, "brief": brief}
    scenario.checklist.payload = payload
    review = init_review(scenario, current_user)
    payload = copy.deepcopy(scenario.checklist.payload)
    payload["review"] = review
    scenario.status = "review_in_progress"
    _save_payload(db, scenario, payload)

    write_audit_log(
        db,
        user=current_user,
        action="sample.create",
        resource_type="scenario",
        resource_id=str(scenario.id),
        detail="一键生成完整协查样本（清单+法源+简报+复核）",
    )

    db.refresh(scenario)
    return scenario_to_response(scenario)


@router.get("/scenarios/{scenario_id}/review", response_model=ReviewResponse)
def get_review(
    scenario_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    scenario = _load_owned_scenario(db, scenario_id, current_user.id)
    review = scenario.checklist.payload.get("review")
    if not review:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="尚未初始化复核，请从简报页进入")
    return ReviewResponse(**review_to_response(scenario_id, review))


@router.post("/scenarios/{scenario_id}/review/init", response_model=ReviewResponse)
def start_review(
    scenario_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    scenario = _load_owned_scenario(db, scenario_id, current_user.id)
    payload = scenario.checklist.payload
    payload = _ensure_brief(scenario, payload)

    review = init_review(scenario, current_user)
    payload = copy.deepcopy(scenario.checklist.payload)
    payload["review"] = review
    scenario.status = "review_in_progress"
    _save_payload(db, scenario, payload)

    write_audit_log(
        db,
        user=current_user,
        action="review.init",
        resource_type="scenario",
        resource_id=str(scenario.id),
        detail=f"初始化法务复核 {len(review.get('items', []))} 条",
    )

    return ReviewResponse(**review_to_response(scenario_id, review))


@router.patch("/scenarios/{scenario_id}/review/items/{item_code}", response_model=ReviewResponse)
def patch_review_item(
    scenario_id: int,
    item_code: str,
    body: ReviewItemUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    scenario = _load_owned_scenario(db, scenario_id, current_user.id)
    review = scenario.checklist.payload.get("review")
    if not review:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="复核尚未初始化")

    try:
        review = update_review_item(
            review,
            code=item_code,
            decision=body.decision,
            comment=body.comment,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    payload = copy.deepcopy(scenario.checklist.payload)
    payload["review"] = review
    _save_payload(db, scenario, payload)

    return ReviewResponse(**review_to_response(scenario_id, review))


@router.post("/scenarios/{scenario_id}/review/approve-all", response_model=ReviewResponse)
def approve_all_review_items(
    scenario_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    scenario = _load_owned_scenario(db, scenario_id, current_user.id)
    review = scenario.checklist.payload.get("review")
    if not review:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="复核尚未初始化")

    try:
        review = approve_all_pending(copy.deepcopy(review))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    payload = copy.deepcopy(scenario.checklist.payload)
    payload["review"] = review
    _save_payload(db, scenario, payload)
    return ReviewResponse(**review_to_response(scenario_id, review))


@router.post("/scenarios/{scenario_id}/review/finalize", response_model=ReviewResponse)
def finalize_scenario_review(
    scenario_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    scenario = _load_owned_scenario(db, scenario_id, current_user.id)
    review = scenario.checklist.payload.get("review")
    if not review:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="复核尚未初始化")

    try:
        review = finalize_review(copy.deepcopy(review))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    payload = copy.deepcopy(scenario.checklist.payload)
    payload["review"] = review
    scenario.status = f"review_{review['status']}"
    _save_payload(db, scenario, payload)

    write_audit_log(
        db,
        user=current_user,
        action="review.finalize",
        resource_type="scenario",
        resource_id=str(scenario.id),
        detail=f"法务复核定稿：{review['status']}",
    )

    return ReviewResponse(**review_to_response(scenario_id, review))


@router.get("/scenarios/{scenario_id}/export/docx")
def export_docx(
    scenario_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    scenario = _load_owned_scenario(db, scenario_id, current_user.id)
    review = scenario.checklist.payload.get("review")
    if not review or not review_to_response(scenario_id, review).get("can_export"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="请先完成法务复核定稿后再导出",
        )

    content, filename = build_sample_docx(scenario)
    write_audit_log(
        db,
        user=current_user,
        action="export.docx",
        resource_type="scenario",
        resource_id=str(scenario.id),
        detail=f"导出协查底稿 {filename}",
    )

    ascii_name = "vela_compliance_brief.docx"
    encoded_name = quote(filename)
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={
            "Content-Disposition": (
                f'attachment; filename="{ascii_name}"; filename*=UTF-8\'\'{encoded_name}'
            )
        },
    )
