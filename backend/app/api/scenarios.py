from __future__ import annotations

from typing import List, Optional
import copy
import json
import logging
from datetime import datetime, timezone
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import FileResponse, Response
from sqlalchemy import update
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.orm.exc import StaleDataError
from starlette.concurrency import run_in_threadpool

from app.core.database import get_db
from app.core.deps import get_current_legal_user, get_current_user
from app.core.roles import ROLE_BUSINESS, ROLE_LEGAL, ROLE_ADMIN, is_legal_role, require_role
from app.models.scenario import InvestigationScenario
from app.models.user import User
from app.schemas.scenario import (
    BusinessSubmitRequest,
    CapabilityPackSummary,
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
from app.services.answerability_gate_service import (
    AnswerabilityGateError,
    require_delivery_answerability,
)
from app.services.delivery_assurance_service import (
    DeliveryAssuranceError,
    DeliveryGateBlocked,
    require_released_delivery_artifact,
)
from app.services.brief_generator import generate_brief
from app.services.document_extractor import extract_documents_batch, extract_facts_from_document
from app.services.export_service import build_sample_docx, build_sample_pdf
from app.services.legal_ingest import get_index_status, ingest_corpus
from app.services.legal_rag import retrieve_for_checklist
from app.services.review_service import (
    ReviewRevisionConflict,
    ReviewStateConflict,
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
    build_deviation_entry,
    persist_deviation_entry,
)
from app.services.user_preference_service import record_review_decision
from app.services.cold_start_service import playbook_scope_hints, resolve_compliance_dimensions
from app.services.material_review_service import assess_material_completeness
from app.services.material_file_storage import resolve_archived_file_path
from app.services.rule_engine import get_demo_scenario_template, get_mining_demo_scenario_template, get_rules_catalog
from app.services.rules_registry import RulesPackNotFoundError, get_classification, list_packs
from app.capability_packs.loader import CapabilityPackLoadError
from app.capability_packs.registry import (
    CapabilityPackNotFoundError,
    CapabilityPackRegistryError,
    get_capability_pack_registry,
)
from app.services.scenario_pipeline import (
    run_business_submit_materials,
    run_confirm_scope_and_generate,
    run_generate_and_submit,
    run_return_materials,
    run_revise_and_resubmit,
    scenario_summary_meta,
)
from app.services.scenario_service import (
    create_scenario_materials_only,
    create_scenario_with_checklist,
    get_demo_request,
    scenario_to_response,
)
from app.services.generation_guard import (
    GenerationConflictError,
    GenerationGuardError,
    require_generated_result,
)
from app.services.scenario_scope_service import (
    match_capability_pack_for_payload,
    material_text_from_uploads,
)
from app.services.upload_security import (
    MAX_BATCH_FILES,
    read_upload_limited,
    read_uploads_limited,
)
from app.services.checklist_payload_service import (
    CHECKLIST_REVISION_CONFLICT_MESSAGE,
    ChecklistRevisionConflict,
    assign_checklist_payload,
    commit_checklist_payload,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["协查场景"])


def _require_delivery_gate(
    db: Session,
    *,
    scenario: InvestigationScenario,
    current_user: User,
    artifact_type: str,
    generation_config,
) -> tuple[dict, object]:
    """Run the final-artifact gate and persist every blocked attempt."""

    try:
        answerability = require_delivery_answerability(db, scenario=scenario)
    except AnswerabilityGateError as exc:
        detail = exc.detail()
        write_audit_log(
            db,
            user=current_user,
            action="delivery.answerability_gate_blocked",
            resource_type="scenario",
            resource_id=str(scenario.id),
            detail=json.dumps(
                {"artifact_type": artifact_type, **detail},
                ensure_ascii=False,
                sort_keys=True,
            ),
        )
        raise HTTPException(status_code=exc.http_status, detail=detail) from exc
    try:
        release, artifact = require_released_delivery_artifact(
            db,
            scenario=scenario,
            generation_config=generation_config,
            artifact_type=artifact_type,
        )
        return {**answerability, "customer_delivery_release": release}, artifact
    except DeliveryGateBlocked as exc:
        write_audit_log(
            db,
            user=current_user,
            action="delivery.customer_release_blocked",
            resource_type="scenario",
            resource_id=str(scenario.id),
            detail=json.dumps(
                {"artifact_type": artifact_type, **exc.report},
                ensure_ascii=False,
                sort_keys=True,
            ),
        )
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=exc.report) from exc
    except DeliveryAssuranceError as exc:
        detail = {"message": str(exc), "artifact_type": artifact_type}
        write_audit_log(
            db,
            user=current_user,
            action="delivery.customer_release_blocked",
            resource_type="scenario",
            resource_id=str(scenario.id),
            detail=json.dumps(detail, ensure_ascii=False, sort_keys=True),
        )
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=detail) from exc


def _save_payload(db: Session, scenario: InvestigationScenario, payload: dict) -> None:
    try:
        commit_checklist_payload(db, scenario, payload)
    except ChecklistRevisionConflict as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


def _commit_review_mutation(
    db: Session,
    scenario: InvestigationScenario,
    payload: dict,
    *,
    current_user: User,
    audit_entries: list[tuple[str, str]],
    new_scenario_status: str | None = None,
) -> None:
    """CAS-save a review mutation and its audit records in one transaction."""

    expected_updated_at = scenario.updated_at
    expected_status = scenario.status
    changed_at = datetime.now(timezone.utc)
    values: dict[str, object] = {"updated_at": changed_at}
    if new_scenario_status is not None:
        values["status"] = new_scenario_status

    result = db.execute(
        update(InvestigationScenario)
        .where(
            InvestigationScenario.id == scenario.id,
            InvestigationScenario.updated_at == expected_updated_at,
            InvestigationScenario.status == expected_status,
        )
        .values(**values)
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="复核内容或场景状态已被其他法务更新，请刷新后重试",
        )

    assign_checklist_payload(scenario, payload)
    try:
        for action, detail in audit_entries:
            write_audit_log(
                db,
                user=current_user,
                action=action,
                resource_type="scenario",
                resource_id=str(scenario.id),
                detail=detail,
                commit=False,
            )
        db.commit()
    except StaleDataError as exc:
        db.rollback()
        raise ChecklistRevisionConflict(CHECKLIST_REVISION_CONFLICT_MESSAGE) from exc
    except Exception:
        db.rollback()
        raise

    scenario.updated_at = changed_at
    if new_scenario_status is not None:
        scenario.status = new_scenario_status


def _review_audit_detail(
    *,
    current_user: User,
    review: dict,
    item: dict | None = None,
    previous: dict | None = None,
    extra: dict | None = None,
) -> str:
    data = {
        "reviewer_id": current_user.id,
        "reviewer_name": current_user.full_name,
        "review_revision": review.get("revision", 0),
        "reviewed_at": (item or {}).get("reviewed_at") or review.get("last_changed_at"),
        "item_code": (item or {}).get("code"),
        "decision": (item or {}).get("decision"),
        "comment": (item or {}).get("comment"),
        "override": bool((item or {}).get("manual_override")),
        "external_counsel_required": bool((item or {}).get("external_counsel_required")),
        "previous": previous,
        **(extra or {}),
    }
    return json.dumps(data, ensure_ascii=False, sort_keys=True)


async def _parse_business_submit_request(
    request: Request,
) -> tuple[BusinessSubmitRequest, list[tuple[str, bytes, str | None]]]:
    content_type = request.headers.get("content-type", "")
    uploads: list[tuple[str, bytes, str | None]] = []
    if content_type.startswith("multipart/form-data"):
        form = await request.form(max_files=MAX_BATCH_FILES, max_fields=5, max_part_size=1024 * 1024)
        raw = form.get("payload")
        if not raw:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="缺少 payload 字段")
        payload = BusinessSubmitRequest.model_validate_json(str(raw))
        file_items = [
            item
            for item in form.getlist("files")
            if isinstance(item, UploadFile) or (hasattr(item, "read") and hasattr(item, "filename"))
        ]
        if file_items:
            content_types = [getattr(item, "content_type", None) for item in file_items]
            try:
                bounded = await read_uploads_limited(file_items)
            except ValueError as exc:
                raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=str(exc)) from exc
            uploads = [
                (filename, content, content_types[index])
                for index, (filename, content) in enumerate(bounded)
            ]
        return payload, uploads
    body = await request.json()
    payload = BusinessSubmitRequest.model_validate(body)
    return payload, uploads


def _require_uploaded_files_if_policy(
    uploads: list[tuple[str, bytes, str | None]],
    payload: BusinessSubmitRequest,
) -> None:
    capability = match_capability_pack_for_payload(
        payload,
        material_text_extra=material_text_from_uploads(uploads),
    )
    policy = capability.rules.get("material_intake_policy") or {}
    if policy.get("philosophy") == "upload_first" and policy.get("archive_source_files") and not uploads:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="请上传投资方案文件后再提交（系统将归档原文件并抽取核对表）",
        )


@router.get("/capability-packs", response_model=list[CapabilityPackSummary])
def capability_packs(_: User = Depends(get_current_user)):
    try:
        return get_capability_pack_registry().list_public_active()
    except (CapabilityPackRegistryError, CapabilityPackLoadError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Capability Pack Registry 不可用：{exc}",
        ) from exc


@router.get("/capability-packs/catalog", response_model=RulesCatalogResponse)
def capability_pack_catalog(_: User = Depends(get_current_user)):
    try:
        return get_rules_catalog()
    except (CapabilityPackRegistryError, CapabilityPackLoadError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Capability Pack catalog 不可用：{exc}",
        ) from exc


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
    pack_id: Optional[str] = Query(default=None, description="兼容参数：Capability Pack ID"),
    _: User = Depends(get_current_user),
):
    try:
        return get_rules_catalog(pack_id)
    except (RulesPackNotFoundError, CapabilityPackNotFoundError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except (CapabilityPackRegistryError, CapabilityPackLoadError) as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


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
    file: UploadFile = File(..., description="投资方案 .txt / .md / .docx / .pdf（≤25MB）"),
    llm_consent: bool = Form(False, description="是否同意本次将材料发送至已批准 LLM Provider"),
    current_user: User = Depends(get_current_user),
):
    """从上传方案抽取客观事实，预填协查表单（规则引擎；配置 LLM 时优先 AI 抽取）。"""
    filename = file.filename or "upload.txt"
    try:
        content = await read_upload_limited(file)
        result = await run_in_threadpool(
            extract_facts_from_document,
            filename,
            content,
            current_user.id,
            llm_consent,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return DocumentExtractResponse(**{"filename": filename, **result})


@router.post("/scenarios/extract-documents", response_model=DocumentExtractBatchResponse)
async def extract_scenario_documents(
    files: List[UploadFile] = File(..., description="投资方案，最多10个（每个≤25MB，合计≤100MB）"),
    llm_consent: bool = Form(False, description="是否同意本次将材料发送至已批准 LLM Provider"),
    current_user: User = Depends(get_current_user),
):
    """逐文件抽取事实，并合并去重为一份预填表单。"""
    if not files:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="请至少上传一个文件")

    try:
        uploads = await read_uploads_limited(files)
        successes, failures, merged, conflicts = await run_in_threadpool(
            extract_documents_batch,
            uploads,
            current_user.id,
            llm_consent,
        )
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


@router.post(
    "/scenarios",
    status_code=status.HTTP_410_GONE,
    deprecated=True,
    summary="已关闭：旧直接生成入口（410 Gone）",
    responses={status.HTTP_410_GONE: {"description": "旧直接生成入口已关闭"}},
)
def create_scenario(
    payload: ScenarioCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail="旧的直接生成清单接口已关闭，请先提交材料并由法务确认 scope",
    )


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
        .filter(InvestigationScenario.is_demo.is_(False))
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
    require_role(current_user, (ROLE_BUSINESS,))
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
    require_role(current_user, (ROLE_BUSINESS,))
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
    """法务将协查案例移入回收站（软删除，可恢复）。"""
    scenario = _load_accessible_scenario(db, scenario_id, current_user)
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
        detail=f"法务删除（移入回收站）：{scenario.project_name}",
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
    if scenario.is_demo:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="正式项目不存在")
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


@router.post(
    "/scenarios/demo/byd-campinas",
    response_model=ScenarioResponse,
    status_code=201,
    deprecated=True,
    summary="隔离演示记录：不可进入正式 Golden Path",
)
def create_demo_scenario(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """创建隔离 demo 记录；不产生正式 business ack，也不能进入正式确认与生成链路。"""
    demo = get_demo_request()
    payload = BusinessSubmitRequest(**demo.model_dump(exclude={"compliance_dimensions"}))
    scenario = create_scenario_materials_only(db, current_user, payload, demo=True)
    return scenario_to_response(scenario)


@router.get(
    "/demo/scenarios",
    response_model=List[ScenarioResponse],
    deprecated=True,
    summary="隔离演示记录列表：非正式 Golden Path",
)
def list_demo_scenarios(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = (
        db.query(InvestigationScenario)
        .options(joinedload(InvestigationScenario.checklist))
        .filter(InvestigationScenario.is_demo.is_(True))
    )
    if not is_legal_role(current_user):
        query = query.filter(InvestigationScenario.user_id == current_user.id)
    return [scenario_to_response(row) for row in query.order_by(InvestigationScenario.created_at.desc()).all()]


@router.get(
    "/demo/scenarios/{scenario_id}",
    response_model=ScenarioResponse,
    deprecated=True,
    summary="读取隔离演示记录：非正式 Golden Path",
)
def get_demo_scenario(
    scenario_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    scenario = _load_scenario_row(db, scenario_id)
    _assert_can_access(scenario, current_user)
    if not scenario.is_demo:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="演示项目不存在")
    return scenario_to_response(scenario)


@router.post(
    "/scenarios/submit-materials",
    response_model=ScenarioResponse,
    status_code=201,
    summary="正式入口：业务提交材料与支持边界知情确认",
)
async def submit_scenario_materials(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """业务：提交项目材料，协查范围由法务确认后再生成清单。"""
    require_role(current_user, (ROLE_BUSINESS,))
    payload, uploads = await _parse_business_submit_request(request)
    try:
        _require_uploaded_files_if_policy(uploads, payload)
        scenario = run_business_submit_materials(db, current_user, payload, uploads=uploads)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return scenario_to_response(scenario)


@router.post(
    "/scenarios/demo/submit-materials",
    response_model=ScenarioResponse,
    status_code=201,
    deprecated=True,
    summary="隔离演示记录：不可进入正式 Golden Path",
)
def submit_demo_materials(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """创建隔离 demo 材料记录；不产生正式 business ack，也不能进入正式确认与生成链路。"""
    require_role(current_user, (ROLE_BUSINESS,))
    from app.services.scenario_service import get_demo_request

    demo = get_demo_request()
    payload = BusinessSubmitRequest(
        **demo.model_dump(exclude={"compliance_dimensions"}),
    )
    scenario = create_scenario_materials_only(db, current_user, payload, demo=True)
    return scenario_to_response(scenario)


@router.post(
    "/scenarios/generate-and-submit",
    status_code=status.HTTP_410_GONE,
    deprecated=True,
    summary="已关闭：旧一键生成并提交入口（410 Gone）",
    responses={status.HTTP_410_GONE: {"description": "旧一键生成入口已关闭"}},
)
def generate_and_submit_scenario(
    payload: ScenarioCreateRequest,
    polish: bool = Query(default=False, description="已忽略的兼容参数；接口不会生成或润色"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """已关闭：不得绕过业务知情、法务确认和快照冻结。"""
    raise HTTPException(status_code=status.HTTP_410_GONE, detail="旧的一键生成接口已关闭")


@router.post(
    "/scenarios/demo/generate-and-submit",
    status_code=status.HTTP_410_GONE,
    deprecated=True,
    summary="已关闭：旧演示一键生成入口（410 Gone）",
    responses={status.HTTP_410_GONE: {"description": "演示一键生成入口已关闭"}},
)
def generate_and_submit_demo(
    polish: bool = Query(default=False, description="已忽略的兼容参数；接口不会生成或润色"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """已关闭：演示记录也不得绕过显式 scope 确认。"""
    raise HTTPException(status_code=status.HTTP_410_GONE, detail="演示一键生成已关闭，请走显式 scope 确认")


@router.post(
    "/scenarios/{scenario_id}/confirm-scope",
    response_model=ScenarioResponse,
    summary="正式入口：法务确认范围、冻结 snapshot 并启动唯一 attempt",
)
def confirm_scenario_scope(
    scenario_id: int,
    body: ScopeConfirmRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_legal_user),
):
    """法务：确认并冻结场景/版本，随后生成协查包。"""
    scenario = _load_accessible_scenario(db, scenario_id, current_user)
    try:
        scenario = run_confirm_scope_and_generate(
            db,
            current_user,
            scenario,
            body.compliance_dimensions,
            polish=body.polish,
            expected_proposal_hash=body.expected_proposal_hash,
            match_threshold=body.match_threshold,
            retrieval_top_k=body.retrieval_top_k,
            include_playbook_suggestions=body.include_playbook_suggestions,
            selected_issue_codes=body.selected_issue_codes,
            fit_decision=body.fit_decision,
        )
    except GenerationConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return scenario_to_response(scenario)


@router.post(
    "/scenarios/{scenario_id}/generate-investigation",
    response_model=ScenarioResponse,
    deprecated=True,
    summary="废弃兼容：执行 confirm-scope 同等硬确认",
)
def generate_investigation_pack(
    scenario_id: int,
    body: ScopeConfirmRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_legal_user),
):
    """兼容旧 URL，但执行与 confirm-scope 相同的硬确认，不允许绕过快照。"""
    scenario = _load_accessible_scenario(db, scenario_id, current_user)
    try:
        scenario = run_confirm_scope_and_generate(
            db,
            current_user,
            scenario,
            body.compliance_dimensions,
            polish=body.polish,
            expected_proposal_hash=body.expected_proposal_hash,
            match_threshold=body.match_threshold,
            retrieval_top_k=body.retrieval_top_k,
            include_playbook_suggestions=body.include_playbook_suggestions,
            selected_issue_codes=body.selected_issue_codes,
            fit_decision=body.fit_decision,
        )
    except GenerationConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return scenario_to_response(scenario)


@router.post(
    "/scenarios/{scenario_id}/retry-generation",
    response_model=ScenarioResponse,
    summary="沿用冻结 snapshot 重试失败的 generation attempt",
)
def retry_investigation_generation(
    scenario_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_legal_user),
):
    """Retry/take over using only the already frozen snapshot; accepts no mutable config."""
    scenario = _load_accessible_scenario(db, scenario_id, current_user)
    snapshot = ((scenario.scenario_scope or {}).get("snapshot") or {})
    proposal = ((scenario.scenario_scope or {}).get("proposed") or {})
    if not snapshot:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="尚未冻结 scope snapshot")
    try:
        scenario = run_confirm_scope_and_generate(
            db,
            current_user,
            scenario,
            list(snapshot.get("compliance_dimensions") or []),
            polish=bool(snapshot.get("polish")),
            expected_proposal_hash=str(proposal.get("proposal_hash") or ""),
            match_threshold=int(snapshot.get("match_threshold") or 0),
            retrieval_top_k=int(snapshot.get("retrieval_top_k") if snapshot.get("retrieval_top_k") is not None else -1),
            include_playbook_suggestions=bool(snapshot.get("include_playbook_suggestions")),
            selected_issue_codes=list(snapshot.get("selected_issue_codes") or []),
            fit_decision=str(snapshot.get("fit_decision") or ""),
        )
    except GenerationConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
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
        owner_identity = {
            "owner_email": current_user.email,
            "owner_auth_provider": current_user.auth_provider,
            "owner_external_subject": current_user.external_subject,
        }
        dims = resolve_compliance_dimensions(
            body.compliance_dimensions,
            user_id=current_user.id,
            **owner_identity,
        )
        if not dims:
            dims = list(body.compliance_dimensions or [])
        result = assess_material_completeness(scenario, dims or list(scenario.compliance_dimensions or []))
        result["playbook_suggestions"] = playbook_scope_hints(current_user.id, **owner_identity)
        payload = scenario.checklist.payload if scenario.checklist else {}
        from app.services.pending_scope_enrichment import enrich_pending_scope_payload

        enriched = enrich_pending_scope_payload(scenario, dict(payload), user_id=current_user.id)
        result["material_scope_findings"] = enriched.get("material_scope_findings") or []
        result["issue_suggestions"] = enriched.get("issue_suggestions") or []
        result["unverified_facts"] = enriched.get("unverified_facts") or []
        doc = enriched.get("document_extract") or {}
        result["document_conflicts"] = doc.get("conflicts") or []
        result["conflict_flags"] = enriched.get("conflict_flags") or []
        if not body.compliance_dimensions and result["playbook_suggestions"].get("default_compliance_dimensions"):
            result["suggested_compliance_dimensions"] = result["playbook_suggestions"][
                "default_compliance_dimensions"
            ]
        return result
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
    if not scenario or scenario.is_demo:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="项目不存在")
    if not is_legal_role(current_user) and scenario.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权下载该文件")

    path = resolve_archived_file_path(scenario_id, stored_name)
    if not path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文件不存在")

    display_name = stored_name.split("__", 1)[1] if "__" in stored_name else stored_name
    return FileResponse(
        path,
        filename=display_name,
        media_type="application/octet-stream",
        headers={
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
            "X-Vela-Content-Screening": "active-content-only-not-antivirus",
        },
    )


@router.post(
    "/scenarios/{scenario_id}/retrieve",
    response_model=LegalRetrievalResponse,
    deprecated=True,
    summary="废弃只读：返回已持久化 RAG（不启动检索）",
)
def retrieve_legal_sources(
    scenario_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Read the persisted retrieval result; this endpoint never starts RAG."""
    scenario = _load_accessible_scenario(db, scenario_id, current_user)
    if not is_legal_role(current_user):
        _assert_owner(scenario, current_user)

    payload = scenario.checklist.payload
    try:
        require_generated_result(db, scenario)
    except GenerationGuardError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    sections = payload.get("sections_with_legal") or []
    retrieval = payload.get("retrieval_meta") or {}

    return LegalRetrievalResponse(
        scenario_id=scenario_id,
        total_hits=sum(len(item.get("legal_hits") or []) for section in sections for item in section.get("items", [])),
        zero_hit_items=list(retrieval.get("zero_hit_items") or []),
        sections=sections,
        disclaimer=retrieval.get("disclaimer") or "已生成法源检索结果（只读）",
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
    if scenario.is_demo:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="正式项目不存在")
    return scenario


def _load_owned_scenario(db: Session, scenario_id: int, user_id: int) -> InvestigationScenario:
    scenario = (
        db.query(InvestigationScenario)
        .options(joinedload(InvestigationScenario.checklist))
        .filter(
            InvestigationScenario.id == scenario_id,
            InvestigationScenario.user_id == user_id,
            InvestigationScenario.is_demo.is_(False),
        )
        .first()
    )
    if scenario is None or scenario.checklist is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="场景或清单不存在")
    return scenario


@router.get(
    "/scenarios/{scenario_id}/brief",
    response_model=BriefGenerateResponse,
    summary="读取已持久化的双语简报",
)
def get_brief(
    scenario_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    scenario = _load_accessible_scenario(db, scenario_id, current_user)
    try:
        require_generated_result(db, scenario)
    except GenerationGuardError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    brief = scenario.checklist.payload.get("brief")
    if not brief:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="协查包中尚无已生成双语简报")
    return BriefGenerateResponse(**brief)


@router.post(
    "/scenarios/{scenario_id}/brief",
    response_model=BriefGenerateResponse,
    deprecated=True,
    summary="废弃只读：返回已持久化简报（不生成、不润色）",
)
def create_brief(
    scenario_id: int,
    polish: bool = Query(default=True, description="已忽略的兼容参数；不会生成或润色简报"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Deprecated read-only POST alias; it never generates or polishes a brief."""
    scenario = _load_accessible_scenario(db, scenario_id, current_user)
    if not is_legal_role(current_user):
        _assert_owner(scenario, current_user)
    try:
        require_generated_result(db, scenario)
    except GenerationGuardError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return BriefGenerateResponse(**scenario.checklist.payload["brief"])


@router.post(
    "/scenarios/{scenario_id}/submit",
    response_model=ScenarioResponse,
    deprecated=True,
    summary="废弃兼容：提交已有生成结果（不启动生成）",
)
def submit_for_legal_review(
    scenario_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Deprecated compatibility action; it consumes an existing result and never starts generation."""
    require_role(current_user, (ROLE_BUSINESS,))
    scenario = _load_owned_scenario(db, scenario_id, current_user.id)
    payload = scenario.checklist.payload
    try:
        require_generated_result(db, scenario)
    except GenerationGuardError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

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
    raise GenerationGuardError("_ensure_brief 必须通过带数据库绑定的 review guard 调用")
    if not payload.get("brief"):
        raise GenerationGuardError("review/init 不得隐式生成简报")
    return payload


@router.post(
    "/scenarios/demo/sample",
    status_code=status.HTTP_410_GONE,
    deprecated=True,
    summary="已关闭：旧完整样本入口（410 Gone）",
    responses={status.HTTP_410_GONE: {"description": "完整样本绕过入口已关闭"}},
)
def create_full_sample(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_legal_user),
):
    raise HTTPException(status_code=status.HTTP_410_GONE, detail="完整样本绕过路径已关闭")


@router.get("/scenarios/{scenario_id}/review", response_model=ReviewResponse)
def get_review(
    scenario_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_legal_user),
):
    scenario = _load_accessible_scenario(db, scenario_id, current_user)
    try:
        require_generated_result(db, scenario)
    except GenerationGuardError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
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
    try:
        require_generated_result(db, scenario)
    except GenerationGuardError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    existing = payload.get("review")
    if existing and existing.get("items"):
        return ReviewResponse(**review_to_response(scenario_id, existing))
    if not payload.get("brief"):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="review/init 不得隐式生成简报")

    review = init_review(db, scenario, current_user)
    payload = copy.deepcopy(scenario.checklist.payload)
    tier_report = payload.get("tier_report") or (payload.get("investigation_adequacy") or {}).get("tier_report")
    if tier_report:
        review["tier_report"] = tier_report
    payload["review"] = review
    _commit_review_mutation(
        db,
        scenario,
        payload,
        current_user=current_user,
        new_scenario_status="review_in_progress",
        audit_entries=[
            (
                "review.init",
                _review_audit_detail(
                    current_user=current_user,
                    review=review,
                    extra={"item_count": len(review.get("items", []))},
                ),
            )
        ],
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
    try:
        require_generated_result(db, scenario)
    except GenerationGuardError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    review = scenario.checklist.payload.get("review")
    if not review:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="复核尚未初始化")

    try:
        review = update_review_item(
            copy.deepcopy(review),
            code=item_code,
            decision=body.decision,
            comment=body.comment,
            external_counsel_required=body.external_counsel_required,
            reviewer_id=current_user.id,
            reviewer_name=current_user.full_name,
            expected_revision=body.expected_revision,
        )
    except (ReviewRevisionConflict, ReviewStateConflict) as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    payload = copy.deepcopy(scenario.checklist.payload)
    payload["review"] = review

    target = next((i for i in review.get("items", []) if i["code"] == item_code), None)
    deviation_entry = None
    if body.decision == "rejected" and target:
        deviation_entry = build_deviation_entry(
            scenario_id=scenario.id,
            project_name=scenario.project_name,
            code=item_code,
            title=target.get("title", item_code),
            comment=body.comment,
            reviewer_name=current_user.full_name,
            match_score=float(target.get("match_score") or 0),
            gate_status=target.get("gate_status", ""),
        )
        payload = append_scenario_deviation(payload, deviation_entry)

    previous = next(
        (
            event.get("previous")
            for event in reversed(review.get("change_history") or [])
            if event.get("action") == "item_updated" and event.get("item_code") == item_code
        ),
        None,
    )
    _commit_review_mutation(
        db,
        scenario,
        payload,
        current_user=current_user,
        audit_entries=[
            (
                "review.item_update",
                _review_audit_detail(
                    current_user=current_user,
                    review=review,
                    item=target,
                    previous=previous,
                ),
            )
        ],
    )

    # Preference/deviation files are advisory learning state, not the source of
    # truth. Write them only after the review + audit transaction succeeds so a
    # rejected CAS request cannot leave a ghost learning event.
    if deviation_entry is not None:
        try:
            persist_deviation_entry(deviation_entry)
        except Exception:
            logger.warning("failed to persist playbook deviation after review commit", exc_info=True)
    try:
        record_review_decision(
            current_user.id,
            code=item_code,
            decision=body.decision,
            comment=body.comment,
            match_score=float((target or {}).get("match_score") or 0),
            tier=(target or {}).get("tier", ""),
        )
    except Exception:
        logger.warning("failed to persist review preference after review commit", exc_info=True)

    return ReviewResponse(**review_to_response(scenario_id, review))


@router.post("/scenarios/{scenario_id}/review/approve-all", response_model=ReviewResponse)
def approve_all_review_items(
    scenario_id: int,
    expected_revision: int = Query(..., ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_legal_user),
):
    scenario = _load_accessible_scenario(db, scenario_id, current_user)
    try:
        require_generated_result(db, scenario)
    except GenerationGuardError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    review = scenario.checklist.payload.get("review")
    if not review:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="复核尚未初始化")

    try:
        review = approve_all_pending(
            copy.deepcopy(review),
            reviewer_id=current_user.id,
            reviewer_name=current_user.full_name,
            expected_revision=expected_revision,
        )
    except (ReviewRevisionConflict, ReviewStateConflict) as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    payload = copy.deepcopy(scenario.checklist.payload)
    payload["review"] = review
    approved_codes = list(review.get("last_bulk_approved_codes") or [])
    approved_items = {
        item.get("code"): item
        for item in review.get("items", [])
        if item.get("code") in approved_codes
    }
    entries = [
        (
            "review.bulk_approve_s1",
            _review_audit_detail(
                current_user=current_user,
                review=review,
                item=approved_items.get(code),
                extra={"bulk": True},
            ),
        )
        for code in approved_codes
    ]
    if not entries:
        entries = [
            (
                "review.bulk_approve_s1",
                _review_audit_detail(
                    current_user=current_user,
                    review=review,
                    extra={"bulk": True, "changed_count": 0},
                ),
            )
        ]
    _commit_review_mutation(
        db,
        scenario,
        payload,
        current_user=current_user,
        audit_entries=entries,
    )
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
    try:
        require_generated_result(db, scenario)
    except GenerationGuardError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    review = scenario.checklist.payload.get("review")
    if not review:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="复核尚未初始化")

    try:
        review = return_review_to_business(
            copy.deepcopy(review),
            current_user,
            note=body.note,
            expected_revision=body.expected_revision,
        )
    except (ReviewRevisionConflict, ReviewStateConflict) as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    payload = copy.deepcopy(scenario.checklist.payload)
    payload["review"] = review
    _commit_review_mutation(
        db,
        scenario,
        payload,
        current_user=current_user,
        new_scenario_status="returned_for_revision",
        audit_entries=[
            (
                "review.return_to_business",
                _review_audit_detail(
                    current_user=current_user,
                    review=review,
                    extra={
                        "status": "returned",
                        "return_note": review.get("return_note"),
                        "rejected_count": review.get("return_snapshot", {}).get("rejected_count", 0),
                    },
                ),
            )
        ],
    )

    db.refresh(scenario)
    return scenario_to_response(scenario)


@router.post("/scenarios/{scenario_id}/review/finalize", response_model=ReviewResponse)
def finalize_scenario_review(
    scenario_id: int,
    expected_revision: int = Query(..., ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_legal_user),
):
    scenario = _load_accessible_scenario(db, scenario_id, current_user)
    try:
        generation_config = require_generated_result(db, scenario)
    except GenerationGuardError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
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
            reviewer_id=current_user.id,
            reviewer_name=current_user.full_name,
            expected_revision=expected_revision,
        )
    except (ReviewRevisionConflict, ReviewStateConflict) as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    payload["review"] = review
    finalize_history.append(
        {
            "version": review.get("version_label"),
            "status": review.get("status"),
            "finalized_at": review.get("finalized_at"),
            "reviewer_id": review.get("finalized_by_id"),
            "reviewer_name": review.get("finalized_by_name"),
            "review_revision": review.get("revision"),
        }
    )
    payload["finalize_history"] = finalize_history
    final_scenario_status = f"review_{review['status']}"
    payload["audit_bundle"] = build_audit_bundle(
        scenario,
        payload_override=payload,
        generation_config=generation_config,
        scenario_status_override=final_scenario_status,
    )
    _commit_review_mutation(
        db,
        scenario,
        payload,
        current_user=current_user,
        new_scenario_status=final_scenario_status,
        audit_entries=[
            (
                "review.finalize",
                _review_audit_detail(
                    current_user=current_user,
                    review=review,
                    extra={
                        "status": review.get("status"),
                        "version_label": review.get("version_label"),
                    },
                ),
            )
        ],
    )

    return ReviewResponse(**review_to_response(scenario_id, review))


@router.get("/scenarios/{scenario_id}/export/audit-bundle")
def export_audit_bundle(
    scenario_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_legal_user),
):
    scenario = _load_accessible_scenario(db, scenario_id, current_user)
    try:
        generation_config = require_generated_result(db, scenario)
    except GenerationGuardError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    review = scenario.checklist.payload.get("review")
    if not review or not review_to_response(scenario_id, review).get("can_export"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="请先完成法务复核定稿后再导出审计包",
        )

    gate, artifact = _require_delivery_gate(
        db,
        scenario=scenario,
        current_user=current_user,
        artifact_type="audit_bundle",
        generation_config=generation_config,
    )
    write_audit_log(
        db,
        user=current_user,
        action="export.audit_bundle",
        resource_type="scenario",
        resource_id=str(scenario.id),
        detail=(f"下载冻结审计包 artifact={artifact.id} sha256={artifact.content_sha256} "
                f"release={gate['customer_delivery_release']['release_hash']}"),
    )
    encoded_name = quote(artifact.filename)
    return Response(
        content=artifact.content,
        media_type=artifact.media_type,
        headers={
            "Content-Disposition": (
                f'attachment; filename="vela_audit_bundle.json"; filename*=UTF-8\'\'{encoded_name}'
            ),
            "X-Content-SHA256": artifact.content_sha256,
            "X-Delivery-Release": gate["customer_delivery_release"]["release_hash"],
        },
    )


@router.get("/scenarios/{scenario_id}/export/docx")
def export_docx(
    scenario_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_legal_user),
):
    scenario = _load_accessible_scenario(db, scenario_id, current_user)
    try:
        generation_config = require_generated_result(db, scenario)
    except GenerationGuardError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    review = scenario.checklist.payload.get("review")
    if not review or not review_to_response(scenario_id, review).get("can_export"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="请先完成法务复核定稿后再导出",
        )

    gate, artifact = _require_delivery_gate(
        db,
        scenario=scenario,
        current_user=current_user,
        artifact_type="docx",
        generation_config=generation_config,
    )
    write_audit_log(
        db,
        user=current_user,
        action="export.docx",
        resource_type="scenario",
        resource_id=str(scenario.id),
        detail=(f"下载冻结 DOCX artifact={artifact.id} sha256={artifact.content_sha256} "
                f"release={gate['customer_delivery_release']['release_hash']}"),
    )

    ascii_name = "vela_compliance_brief.docx"
    encoded_name = quote(artifact.filename)
    return Response(
        content=artifact.content,
        media_type=artifact.media_type,
        headers={
            "Content-Disposition": (
                f'attachment; filename="{ascii_name}"; filename*=UTF-8\'\'{encoded_name}'
            ),
            "X-Content-SHA256": artifact.content_sha256,
            "X-Delivery-Release": gate["customer_delivery_release"]["release_hash"],
        },
    )


@router.get("/scenarios/{scenario_id}/export/pdf")
def export_pdf(
    scenario_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_legal_user),
):
    scenario = _load_accessible_scenario(db, scenario_id, current_user)
    try:
        generation_config = require_generated_result(db, scenario)
    except GenerationGuardError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    review = scenario.checklist.payload.get("review")
    if not review or not review_to_response(scenario_id, review).get("can_export"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="请先完成法务复核定稿后再导出",
        )

    gate, artifact = _require_delivery_gate(
        db,
        scenario=scenario,
        current_user=current_user,
        artifact_type="pdf",
        generation_config=generation_config,
    )
    write_audit_log(
        db,
        user=current_user,
        action="export.pdf",
        resource_type="scenario",
        resource_id=str(scenario.id),
        detail=(f"下载冻结 PDF artifact={artifact.id} sha256={artifact.content_sha256} "
                f"release={gate['customer_delivery_release']['release_hash']}"),
    )

    ascii_name = "vela_compliance_brief.pdf"
    encoded_name = quote(artifact.filename)
    return Response(
        content=artifact.content,
        media_type=artifact.media_type,
        headers={
            "Content-Disposition": (
                f'attachment; filename="{ascii_name}"; filename*=UTF-8\'\'{encoded_name}'
            ),
            "X-Content-SHA256": artifact.content_sha256,
            "X-Delivery-Release": gate["customer_delivery_release"]["release_hash"],
        },
    )
