from __future__ import annotations

from typing import List, Optional
import copy
from datetime import datetime, timezone
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import FileResponse, Response
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.orm.attributes import flag_modified

from app.core.database import get_db
from app.core.deps import get_current_legal_user, get_current_user
from app.core.roles import ROLE_BUSINESS, ROLE_LEGAL, ROLE_ADMIN, is_legal_role, require_role
from app.models.scenario import InvestigationScenario
from app.models.user import User
from app.schemas.scenario import (
    BusinessSubmitRequest,
    MaterialReturnRequest,
    MaterialReviewPreviewRequest,
    RulesCatalogResponse,
    RulesClassificationResponse,
    RulesPackSummary,
    ScenarioCreateRequest,
    ScenarioResponse,
    ScenarioSummary,
    ScopeConfirmRequest,
)
from app.schemas.brief import BriefGenerateResponse
from app.schemas.document import DocumentExtractBatchResponse, DocumentExtractResponse, FieldConflict
from app.schemas.legal import LegalRetrievalResponse
from app.schemas.review import ReviewItemUpdateRequest, ReviewResponse, ReviewReturnRequest
from app.services.audit import write_audit_log
from app.services.audit_bundle_service import build_audit_bundle
from app.services.brief_generator import generate_brief
from app.services.document_extractor import extract_documents_batch, extract_facts_from_document
from app.services.export_service import build_sample_docx, build_sample_pdf
from app.services.legal_ingest import get_index_status, ingest_corpus
from app.services.legal_rag import retrieve_for_checklist
from app.services.review_service import (
    approve_all_pending,
    business_feedback_from_review,
    return_review_to_business,
    finalize_review,
    init_review,
    review_to_response,
    update_review_item,
)
from app.services.playbook_deviation_service import (
    append_scenario_deviation,
    record_deviation,
)
from app.services.user_preference_service import record_review_decision
from app.services.material_review_service import assess_material_completeness
from app.services.material_file_storage import resolve_archived_file_path
from app.services.rule_engine import get_demo_scenario_template, get_mining_demo_scenario_template, get_rules_catalog, load_rules
from app.services.rules_registry import RulesPackNotFoundError, get_classification, list_packs, resolve_pack_id
from app.services.scenario_pipeline import (
    run_business_submit_materials,
    run_generate_investigation_pack,
    run_generate_and_submit,
    run_return_materials,
    run_revise_and_resubmit,
    scenario_summary_meta,
)
from app.services.scenario_service import create_scenario_with_checklist, get_demo_request, scenario_to_response

router = APIRouter(tags=["协查场景"])


def _save_payload(db: Session, scenario: InvestigationScenario, payload: dict) -> None:
    scenario.checklist.payload = copy.deepcopy(payload)
    flag_modified(scenario.checklist, "payload")
    db.commit()


async def _parse_business_submit_request(
    request: Request,
) -> tuple[BusinessSubmitRequest, list[tuple[str, bytes, str | None]]]:
    content_type = request.headers.get("content-type", "")
    uploads: list[tuple[str, bytes, str | None]] = []
    if content_type.startswith("multipart/form-data"):
        form = await request.form()
        raw = form.get("payload")
        if not raw:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="缺少 payload 字段")
        payload = BusinessSubmitRequest.model_validate_json(str(raw))
        for item in form.getlist("files"):
            if isinstance(item, UploadFile):
                content = await item.read()
                uploads.append((item.filename or "upload.bin", content, item.content_type))
        return payload, uploads
    body = await request.json()
    payload = BusinessSubmitRequest.model_validate(body)
    return payload, uploads


def _require_uploaded_files_if_policy(uploads: list[tuple[str, bytes, str | None]]) -> None:
    policy = load_rules().get("material_intake_policy") or {}
    if policy.get("philosophy") == "upload_first" and policy.get("archive_source_files") and not uploads:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="请上传投资方案文件后再提交（系统将归档原文件并抽取核对表）",
        )


@router.get("/rules/classification", response_model=RulesClassificationResponse)
def rules_classification(_: User = Depends(get_current_user)):
    return get_classification()


@router.get("/rules/packs", response_model=list[RulesPackSummary])
def rules_packs(
    include_planned: bool = Query(default=False),
    _: User = Depends(get_current_user),
):
    return list_packs(include_planned=include_planned)


@router.get("/rules/catalog", response_model=RulesCatalogResponse)
def rules_catalog(
    pack_id: Optional[str] = Query(default=None, description="规则包 ID，默认使用 index.json 中的 default_pack_id"),
    _: User = Depends(get_current_user),
):
    try:
        return get_rules_catalog(pack_id)
    except RulesPackNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/rules/demo-template")
def demo_template(_: User = Depends(get_current_user)):
    return get_demo_scenario_template()


@router.get("/rules/demo-template/mining")
def mining_demo_template(_: User = Depends(get_current_user)):
    try:
        return get_mining_demo_scenario_template()
    except ValueError as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc


@router.post("/scenarios/extract-document", response_model=DocumentExtractResponse)
async def extract_scenario_document(
    file: UploadFile = File(..., description="投资方案 .txt / .md / .docx / .pdf（≤200MB）"),
    _: User = Depends(get_current_user),
):
    """从上传方案抽取客观事实，预填协查表单（规则引擎；配置 LLM 时优先 AI 抽取）。"""
    filename = file.filename or "upload.txt"
    content = await file.read()
    try:
        result = extract_facts_from_document(filename, content)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return DocumentExtractResponse(filename=filename, **result)


@router.post("/scenarios/extract-documents", response_model=DocumentExtractBatchResponse)
async def extract_scenario_documents(
    files: List[UploadFile] = File(..., description="投资方案，可上传多个（每个≤200MB，合计≤2GB）"),
    _: User = Depends(get_current_user),
):
    """逐文件抽取事实，并合并去重为一份预填表单。"""
    if not files:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="请至少上传一个文件")

    uploads: list[tuple[str, bytes]] = []
    for upload in files:
        filename = upload.filename or "upload.txt"
        content = await upload.read()
        uploads.append((filename, content))

    try:
        successes, failures, merged, conflicts = extract_documents_batch(uploads)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    per_file = [DocumentExtractResponse(filename=filename, **result) for filename, result in successes]
    if len(successes) == 1:
        merged_filename = successes[0][0]
    elif len(successes) <= 3:
        merged_filename = "、".join(filename for filename, _ in successes)
    else:
        merged_filename = f"{len(successes)} 个文件"

    merged_response = DocumentExtractResponse(filename=merged_filename, **merged)
    if failures:
        merged_response = merged_response.model_copy(
            update={
                "disclaimer": merged_response.disclaimer
                + f" 以下文件抽取失败已跳过：{'；'.join(failures)}"
            }
        )

    return DocumentExtractBatchResponse(
        files=per_file,
        merged=merged_response,
        failed=failures,
        conflicts=[FieldConflict(**item) for item in conflicts],
    )


@router.post("/scenarios", response_model=ScenarioResponse, status_code=201)
def create_scenario(
    payload: ScenarioCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if len(payload.compliance_dimensions) < 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="请至少选择一个合规审查维度",
        )
    scenario = create_scenario_with_checklist(db, current_user, payload)
    return scenario_to_response(scenario)


@router.get("/scenarios", response_model=List[ScenarioSummary])
def list_scenarios(
    include_archived: bool = Query(default=False, description="业务端：是否包含已移入回收站的项目"),
    include_deleted: bool = Query(default=False, description="法务端：是否包含已移入回收站的项目"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = (
        db.query(InvestigationScenario, User)
        .join(User, InvestigationScenario.user_id == User.id)
        .options(joinedload(InvestigationScenario.checklist))
    )
    if not is_legal_role(current_user):
        query = query.filter(InvestigationScenario.user_id == current_user.id)
        if not include_archived:
            query = query.filter(InvestigationScenario.business_archived_at.is_(None))
    elif not include_deleted:
        query = query.filter(InvestigationScenario.legal_deleted_at.is_(None))

    rows = query.order_by(InvestigationScenario.created_at.desc()).all()
    summaries: list[ScenarioSummary] = []
    for s, owner in rows:
        payload = s.checklist.payload if s.checklist else {}
        meta = scenario_summary_meta(s.status, payload)
        bf = business_feedback_from_review(payload.get("review"))
        summaries.append(
            ScenarioSummary(
                id=s.id,
                project_name=s.project_name,
                city=s.city,
                industry=s.industry,
                status=s.status,
                total_items=s.checklist.total_items if s.checklist else None,
                created_at=s.created_at,
                submitter_name=owner.full_name if is_legal_role(current_user) else None,
                submitter_organization=owner.organization if is_legal_role(current_user) else None,
                progress_status=meta["progress_status"],
                review_priority=meta["review_priority"],
                blocked_count=meta["blocked_count"],
                passed_count=meta["passed_count"],
                legal_rejected_count=bf.get("rejected_count") if bf else None,
                feedback_action_required=bf.get("action_required") if bf else None,
                needs_revision=meta.get("needs_revision"),
                business_archived=bool(s.business_archived_at),
                legal_deleted=bool(s.legal_deleted_at),
                legal_deleted_at=s.legal_deleted_at,
                has_document_extract=bool(payload.get("document_extract")),
            )
        )

    if is_legal_role(current_user):
        summaries.sort(
            key=lambda item: (
                0 if item.status == "pending_scope" else 1 if item.status == "pending_legal_review" else 2,
                {"high": 0, "medium": 1, "low": 2}.get(item.review_priority or "low", 9),
                -item.created_at.timestamp(),
            )
        )
    return summaries


@router.post("/scenarios/{scenario_id}/archive")
def archive_scenario_for_business(
    scenario_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_role(current_user, ROLE_BUSINESS)
    scenario = _load_owned_scenario(db, scenario_id, current_user.id)
    if scenario.status == "returned_for_revision":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="该项目待补充材料，请先处理法务反馈后再移入回收站",
        )
    scenario.business_archived_at = datetime.now(timezone.utc)
    db.commit()
    write_audit_log(
        db,
        user=current_user,
        action="scenario.archive",
        resource_type="scenario",
        resource_id=str(scenario.id),
        detail=f"业务移入回收站：{scenario.project_name}",
    )
    return {"ok": True, "id": scenario.id}


@router.post("/scenarios/{scenario_id}/unarchive")
def unarchive_scenario_for_business(
    scenario_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_role(current_user, ROLE_BUSINESS)
    scenario = _load_owned_scenario(db, scenario_id, current_user.id)
    scenario.business_archived_at = None
    db.commit()
    write_audit_log(
        db,
        user=current_user,
        action="scenario.unarchive",
        resource_type="scenario",
        resource_id=str(scenario.id),
        detail=f"业务从回收站恢复：{scenario.project_name}",
    )
    return {"ok": True, "id": scenario.id}


@router.delete("/scenarios/{scenario_id}")
def delete_scenario(
    scenario_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_legal_user),
):
    """法务将已定稿协查案例移入回收站（可恢复）。"""
    scenario = _load_accessible_scenario(db, scenario_id, current_user)
    payload = scenario.checklist.payload if scenario.checklist else {}
    meta = scenario_summary_meta(scenario.status, payload)
    progress = meta["progress_status"]

    if progress in ("submitted", "in_review"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="待法务复核或复核中的项目不可移入回收站",
        )
    if progress == "needs_revision":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="待业务补充的项目不可移入回收站，请等待业务重提或继续跟进",
        )
    if progress != "finalized":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="仅已定稿项目可移入回收站；历史半成品请确认无进行中的复核后再联系管理员清理",
        )
    if scenario.legal_deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="该项目已在回收站中",
        )

    scenario.legal_deleted_at = datetime.now(timezone.utc)
    db.commit()
    write_audit_log(
        db,
        user=current_user,
        action="scenario.delete",
        resource_type="scenario",
        resource_id=str(scenario_id),
        detail=f"法务移入回收站：{scenario.project_name}",
    )
    return {"ok": True, "id": scenario_id}


@router.post("/scenarios/{scenario_id}/restore")
def restore_scenario_for_legal(
    scenario_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_legal_user),
):
    """法务从回收站恢复协查案例。"""
    scenario = _load_scenario_row(db, scenario_id)
    if scenario.legal_deleted_at is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="该项目不在回收站中",
        )

    project_name = scenario.project_name
    scenario.legal_deleted_at = None
    db.commit()
    write_audit_log(
        db,
        user=current_user,
        action="scenario.restore",
        resource_type="scenario",
        resource_id=str(scenario.id),
        detail=f"法务从回收站恢复：{project_name}",
    )
    return {"ok": True, "id": scenario.id}


@router.get("/scenarios/{scenario_id}", response_model=ScenarioResponse)
def get_scenario(
    scenario_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    scenario = _load_accessible_scenario(db, scenario_id, current_user)
    return scenario_to_response(scenario)


@router.post("/scenarios/demo/byd-campinas", response_model=ScenarioResponse, status_code=201)
def create_demo_scenario(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    payload = get_demo_request()
    scenario = create_scenario_with_checklist(db, current_user, payload)
    return scenario_to_response(scenario)


@router.post("/scenarios/submit-materials", response_model=ScenarioResponse, status_code=201)
async def submit_scenario_materials(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """业务：提交项目材料，协查范围由法务确认后再生成清单。"""
    require_role(current_user, (ROLE_BUSINESS,))
    payload, uploads = await _parse_business_submit_request(request)
    _require_uploaded_files_if_policy(uploads)
    scenario = run_business_submit_materials(db, current_user, payload, uploads=uploads)
    return scenario_to_response(scenario)


@router.post("/scenarios/demo/submit-materials", response_model=ScenarioResponse, status_code=201)
def submit_demo_materials(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """业务：BYD 演示模板材料提交（待法务确认协查范围）。"""
    require_role(current_user, (ROLE_BUSINESS,))
    from app.services.scenario_service import get_demo_request

    demo = get_demo_request()
    payload = BusinessSubmitRequest(**demo.model_dump(exclude={"compliance_dimensions"}))
    scenario = run_business_submit_materials(db, current_user, payload)
    return scenario_to_response(scenario)


@router.post("/scenarios/generate-and-submit", response_model=ScenarioResponse, status_code=201)
def generate_and_submit_scenario(
    payload: ScenarioCreateRequest,
    polish: bool = Query(default=False, description="启用 LLM 润色（较慢，可选）"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """法务一键：生成清单 + 法源 + 简报并进入待复核（兼容旧接口）。"""
    require_role(current_user, (ROLE_LEGAL, ROLE_ADMIN))
    if len(payload.compliance_dimensions) < 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="请至少选择一个合规审查维度",
        )
    scenario = run_generate_and_submit(db, current_user, payload, polish=polish)
    return scenario_to_response(scenario)


@router.post("/scenarios/demo/generate-and-submit", response_model=ScenarioResponse, status_code=201)
def generate_and_submit_demo(
    polish: bool = Query(default=False),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """法务：BYD 演示模板一键生成并进入待复核。"""
    require_role(current_user, (ROLE_LEGAL, ROLE_ADMIN))
    scenario = run_generate_and_submit(db, current_user, get_demo_request(), polish=polish)
    return scenario_to_response(scenario)


@router.post("/scenarios/{scenario_id}/confirm-scope", response_model=ScenarioResponse)
def confirm_scenario_scope(
    scenario_id: int,
    body: ScopeConfirmRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_legal_user),
):
    """法务：生成协查包（清单 + 法源 + 匹配度 + 简报）。兼容旧路径 confirm-scope。"""
    scenario = _load_accessible_scenario(db, scenario_id, current_user)
    try:
        scenario = run_generate_investigation_pack(
            db,
            current_user,
            scenario,
            body.compliance_dimensions,
            polish=body.polish,
            match_threshold=body.match_threshold,
            retrieval_top_k=body.retrieval_top_k,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return scenario_to_response(scenario)


@router.post("/scenarios/{scenario_id}/generate-investigation", response_model=ScenarioResponse)
def generate_investigation_pack(
    scenario_id: int,
    body: ScopeConfirmRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_legal_user),
):
    """法务：选定维度并一次生成协查包，进入统一复核。"""
    scenario = _load_accessible_scenario(db, scenario_id, current_user)
    try:
        scenario = run_generate_investigation_pack(
            db,
            current_user,
            scenario,
            body.compliance_dimensions,
            polish=body.polish,
            match_threshold=body.match_threshold,
            retrieval_top_k=body.retrieval_top_k,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return scenario_to_response(scenario)


@router.post("/scenarios/{scenario_id}/material-review/preview")
def preview_material_review(
    scenario_id: int,
    body: MaterialReviewPreviewRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_legal_user),
):
    """法务：材料预检（仅供参考，不阻断生成协查包）。"""
    scenario = _load_accessible_scenario(db, scenario_id, current_user)
    if scenario.status != "pending_scope":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="仅待生成协查包的项目可预览材料预检",
        )
    try:
        return assess_material_completeness(scenario, body.compliance_dimensions)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/scenarios/{scenario_id}/return-materials", response_model=ScenarioResponse)
def return_scenario_materials(
    scenario_id: int,
    body: MaterialReturnRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_legal_user),
):
    """法务：打回业务补充材料（构成要件/字段）；协查未定稿前均可操作。"""
    scenario = _load_accessible_scenario(db, scenario_id, current_user)
    try:
        scenario = run_return_materials(
            db,
            current_user,
            scenario,
            body.compliance_dimensions,
            body.missing_fields,
            missing_elements=body.missing_elements,
            note=body.note,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return scenario_to_response(scenario)


@router.post("/scenarios/{scenario_id}/revise-and-resubmit", response_model=ScenarioResponse)
async def revise_and_resubmit_scenario(
    scenario_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """业务：法务退回后在同一项目补充材料并重新提交（待法务再次确认范围）。"""
    require_role(current_user, (ROLE_BUSINESS,))
    scenario = _load_owned_scenario(db, scenario_id, current_user.id)
    payload, uploads = await _parse_business_submit_request(request)
    try:
        scenario = run_revise_and_resubmit(db, current_user, scenario, payload, uploads=uploads)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return scenario_to_response(scenario)


@router.get("/scenarios/{scenario_id}/material-files/{stored_name}")
def download_scenario_material_file(
    scenario_id: int,
    stored_name: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """下载业务提交时归档的原始方案文件（业务本人或法务）。"""
    scenario = db.query(InvestigationScenario).filter(InvestigationScenario.id == scenario_id).first()
    if not scenario:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="项目不存在")
    if not is_legal_role(current_user) and scenario.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权下载该文件")

    path = resolve_archived_file_path(scenario_id, stored_name)
    if not path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文件不存在")

    display_name = stored_name.split("__", 1)[1] if "__" in stored_name else stored_name
    return FileResponse(path, filename=display_name, media_type="application/octet-stream")


@router.post("/scenarios/{scenario_id}/retrieve", response_model=LegalRetrievalResponse)
def retrieve_legal_sources(
    scenario_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    scenario = _load_accessible_scenario(db, scenario_id, current_user)
    if not is_legal_role(current_user):
        _assert_owner(scenario, current_user)

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


def _load_scenario_row(
    db: Session,
    scenario_id: int,
    *,
    require_checklist: bool = True,
) -> InvestigationScenario:
    scenario = (
        db.query(InvestigationScenario)
        .options(joinedload(InvestigationScenario.checklist))
        .filter(InvestigationScenario.id == scenario_id)
        .first()
    )
    if scenario is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="场景不存在")
    if require_checklist and scenario.checklist is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="场景或清单不存在")
    return scenario


def _assert_can_access(scenario: InvestigationScenario, user: User) -> None:
    if scenario.user_id != user.id and not is_legal_role(user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权访问该协查场景")


def _assert_owner(scenario: InvestigationScenario, user: User) -> None:
    if scenario.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="仅场景提交人可执行此操作")


def _assert_not_legally_deleted(scenario: InvestigationScenario, user: User) -> None:
    if scenario.legal_deleted_at is not None and is_legal_role(user):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="场景不存在或已移入回收站")


def _load_accessible_scenario(db: Session, scenario_id: int, user: User) -> InvestigationScenario:
    scenario = _load_scenario_row(db, scenario_id)
    _assert_can_access(scenario, user)
    _assert_not_legally_deleted(scenario, user)
    return scenario


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
    scenario = _load_accessible_scenario(db, scenario_id, current_user)
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
    scenario = _load_accessible_scenario(db, scenario_id, current_user)
    if not is_legal_role(current_user):
        _assert_owner(scenario, current_user)
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


@router.post("/scenarios/{scenario_id}/submit", response_model=ScenarioResponse)
def submit_for_legal_review(
    scenario_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """业务提交人：将已生成简报的场景提交法务复核。"""
    require_role(current_user, (ROLE_BUSINESS,))
    scenario = _load_owned_scenario(db, scenario_id, current_user.id)
    payload = scenario.checklist.payload

    if not payload.get("brief"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="请先生成双语简报后再提交法务复核")

    if scenario.status == "pending_legal_review":
        return scenario_to_response(scenario)

    if scenario.status.startswith("review_"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="该场景已进入或完成法务复核")

    scenario.status = "pending_legal_review"
    db.commit()
    db.refresh(scenario)

    write_audit_log(
        db,
        user=current_user,
        action="scenario.submit",
        resource_type="scenario",
        resource_id=str(scenario.id),
        detail=f"提交法务复核：{scenario.project_name}",
    )

    return scenario_to_response(scenario)


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
    current_user: User = Depends(get_current_legal_user),
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
    current_user: User = Depends(get_current_legal_user),
):
    scenario = _load_accessible_scenario(db, scenario_id, current_user)
    review = scenario.checklist.payload.get("review")
    if not review:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="尚未初始化复核，请从简报页进入")
    return ReviewResponse(**review_to_response(scenario_id, review))


@router.post("/scenarios/{scenario_id}/review/init", response_model=ReviewResponse)
def start_review(
    scenario_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_legal_user),
):
    scenario = _load_accessible_scenario(db, scenario_id, current_user)
    payload = scenario.checklist.payload
    payload = _ensure_brief(scenario, payload)

    review = init_review(scenario, current_user)
    payload = copy.deepcopy(scenario.checklist.payload)
    tier_report = payload.get("tier_report") or (payload.get("investigation_adequacy") or {}).get("tier_report")
    if tier_report:
        review["tier_report"] = tier_report
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
    current_user: User = Depends(get_current_legal_user),
):
    scenario = _load_accessible_scenario(db, scenario_id, current_user)
    review = scenario.checklist.payload.get("review")
    if not review:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="复核尚未初始化")

    try:
        review = update_review_item(
            review,
            code=item_code,
            decision=body.decision,
            comment=body.comment,
            external_counsel_required=body.external_counsel_required,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    payload = copy.deepcopy(scenario.checklist.payload)
    payload["review"] = review

    target = next((i for i in review.get("items", []) if i["code"] == item_code), None)
    if body.decision == "rejected" and target:
        entry = record_deviation(
            scenario_id=scenario.id,
            project_name=scenario.project_name,
            code=item_code,
            title=target.get("title", item_code),
            comment=body.comment,
            reviewer_name=current_user.full_name,
            match_score=float(target.get("match_score") or 0),
            gate_status=target.get("gate_status", ""),
        )
        payload = append_scenario_deviation(payload, entry)

    record_review_decision(
        current_user.id,
        code=item_code,
        decision=body.decision,
        comment=body.comment,
        match_score=float((target or {}).get("match_score") or 0),
        tier=(target or {}).get("tier", ""),
    )

    _save_payload(db, scenario, payload)

    return ReviewResponse(**review_to_response(scenario_id, review))


@router.post("/scenarios/{scenario_id}/review/approve-all", response_model=ReviewResponse)
def approve_all_review_items(
    scenario_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_legal_user),
):
    scenario = _load_accessible_scenario(db, scenario_id, current_user)
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


@router.post("/scenarios/{scenario_id}/review/return-to-business", response_model=ScenarioResponse)
def return_scenario_to_business(
    scenario_id: int,
    body: ReviewReturnRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_legal_user),
):
    """法务：将含驳回条目的复核退回业务，在同一项目补充后重新提交。"""
    scenario = _load_accessible_scenario(db, scenario_id, current_user)
    review = scenario.checklist.payload.get("review")
    if not review:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="复核尚未初始化")

    try:
        review = return_review_to_business(copy.deepcopy(review), current_user, note=body.note)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    payload = copy.deepcopy(scenario.checklist.payload)
    payload["review"] = review
    scenario.status = "returned_for_revision"
    _save_payload(db, scenario, payload)

    write_audit_log(
        db,
        user=current_user,
        action="review.return_to_business",
        resource_type="scenario",
        resource_id=str(scenario.id),
        detail=f"退回业务补充：{scenario.project_name}（驳回 {review.get('return_snapshot', {}).get('rejected_count', 0)} 条）",
    )

    db.refresh(scenario)
    return scenario_to_response(scenario)


@router.post("/scenarios/{scenario_id}/review/finalize", response_model=ReviewResponse)
def finalize_scenario_review(
    scenario_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_legal_user),
):
    scenario = _load_accessible_scenario(db, scenario_id, current_user)
    review = scenario.checklist.payload.get("review")
    if not review:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="复核尚未初始化")

    try:
        payload = copy.deepcopy(scenario.checklist.payload)
        revision_round = int(payload.get("revision_round") or 0)
        finalize_history = list(payload.get("finalize_history") or [])
        finalize_seq = len(finalize_history)
        review = finalize_review(
            copy.deepcopy(review),
            revision_round=revision_round,
            finalize_seq=finalize_seq,
            tier_report=payload.get("tier_report") or (payload.get("investigation_adequacy") or {}).get("tier_report"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    payload["review"] = review
    finalize_history.append(
        {
            "version": review.get("version_label"),
            "status": review.get("status"),
            "finalized_at": review.get("finalized_at"),
        }
    )
    payload["finalize_history"] = finalize_history
    payload["audit_bundle"] = build_audit_bundle(scenario, payload_override=payload)
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


@router.get("/scenarios/{scenario_id}/export/audit-bundle")
def export_audit_bundle(
    scenario_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_legal_user),
):
    scenario = _load_accessible_scenario(db, scenario_id, current_user)
    review = scenario.checklist.payload.get("review")
    if not review or not review_to_response(scenario_id, review).get("can_export"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="请先完成法务复核定稿后再导出审计包",
        )

    bundle = scenario.checklist.payload.get("audit_bundle") or build_audit_bundle(scenario)
    write_audit_log(
        db,
        user=current_user,
        action="export.audit_bundle",
        resource_type="scenario",
        resource_id=str(scenario.id),
        detail=f"导出审计包 v{bundle.get('bundle_version')}",
    )
    return bundle


@router.get("/scenarios/{scenario_id}/export/docx")
def export_docx(
    scenario_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_legal_user),
):
    scenario = _load_accessible_scenario(db, scenario_id, current_user)
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


@router.get("/scenarios/{scenario_id}/export/pdf")
def export_pdf(
    scenario_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_legal_user),
):
    scenario = _load_accessible_scenario(db, scenario_id, current_user)
    review = scenario.checklist.payload.get("review")
    if not review or not review_to_response(scenario_id, review).get("can_export"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="请先完成法务复核定稿后再导出",
        )

    content, filename = build_sample_pdf(scenario)
    write_audit_log(
        db,
        user=current_user,
        action="export.pdf",
        resource_type="scenario",
        resource_id=str(scenario.id),
        detail=f"导出 PDF 协查底稿 {filename}",
    )

    ascii_name = "vela_compliance_brief.pdf"
    encoded_name = quote(filename)
    return Response(
        content=content,
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                f'attachment; filename="{ascii_name}"; filename*=UTF-8\'\'{encoded_name}'
            )
        },
    )
