from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import or_

from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.roles import is_legal_role
from app.models.mechanism import ClaimCompilation, ClaimRecord, FactRecord, ResearchItem
from app.models.audit_log import AuditLog
from app.models.scenario import InvestigationScenario
from app.models.user import User
from app.schemas.mechanism import (
    ClaimCompilationResponse,
    ClaimCompileRequest,
    ClaimConfirmRequest,
    ClaimRecordResponse,
    CoverageProofCreateRequest,
    CoverageProofResponse,
    CoverageTaskCreateRequest,
    CoverageTaskResponse,
    FactConfirmRequest,
    FactRecordCreateRequest,
    FactRecordResponse,
    MaterialLedgerResponse,
    MaterialLedgerUpsertRequest,
    MechanismAuditEventResponse,
    ResearchItemDecisionRequest,
    ResearchItemResponse,
)
from app.services.audit import write_audit_log
from app.services.mechanism_service import (
    MechanismConflict,
    MechanismValidationError,
    compilation_claims,
    compilation_research_items,
    compile_claims,
    confirm_fact_record,
    confirm_claim,
    create_coverage_proof,
    create_coverage_task,
    create_fact_record,
    decide_research_item,
    latest_compilation,
    latest_coverage_proof,
    list_coverage_tasks,
    list_fact_records,
    list_material_ledger_entries,
    upsert_material_ledger_entry,
)


router = APIRouter(tags=["机制层"])


def _load_scenario(db: Session, scenario_id: int, user: User) -> InvestigationScenario:
    scenario = (
        db.query(InvestigationScenario)
        .options(joinedload(InvestigationScenario.checklist))
        .filter(
            InvestigationScenario.id == scenario_id,
            InvestigationScenario.is_demo.is_(False),
        )
        .first()
    )
    if scenario is None or scenario.checklist is None or scenario.legal_deleted_at is not None:
        raise HTTPException(status_code=404, detail="正式协查场景不存在")
    if scenario.user_id != user.id and not is_legal_role(user):
        raise HTTPException(status_code=403, detail="无权访问该协查场景")
    return scenario


def _require_legal(user: User) -> None:
    if not is_legal_role(user):
        raise HTTPException(status_code=403, detail="该机制层操作必须由法务人工执行")


def _raise_service_error(exc: Exception) -> None:
    if isinstance(exc, MechanismConflict):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc


def _compilation_response(
    compilation: ClaimCompilation,
    claims: list[ClaimRecord],
    research_items: list[ResearchItem] | None = None,
) -> ClaimCompilationResponse:
    return ClaimCompilationResponse(
        id=compilation.id,
        scenario_id=compilation.scenario_id,
        compiler_version=compilation.compiler_version,
        input_hash=compilation.input_hash,
        output_hash=compilation.output_hash,
        denominator_count=compilation.denominator_count,
        ready_count=compilation.ready_count,
        refused_count=compilation.refused_count,
        input_snapshot=compilation.input_snapshot,
        created_by=compilation.created_by,
        created_at=compilation.created_at,
        claims=[ClaimRecordResponse.model_validate(claim) for claim in claims],
        research_items=[
            ResearchItemResponse.model_validate(item)
            for item in (research_items or [])
        ],
    )


def _coverage_task_response(task) -> CoverageTaskResponse:
    denominator_count = len(task.denominator_items or [])
    covered_count = len(task.covered_items or [])
    return CoverageTaskResponse(
        id=task.id,
        scenario_id=task.scenario_id,
        source=task.source,
        state=task.state,
        denominator_ref=task.denominator_ref,
        denominator_snapshot_hash=task.denominator_snapshot_hash,
        denominator_items=list(task.denominator_items or []),
        covered_items=list(task.covered_items or []),
        denominator_count=denominator_count,
        covered_count=covered_count,
        missing_count=denominator_count - covered_count,
        note=task.note,
        created_by=task.created_by,
        created_at=task.created_at,
        updated_at=task.updated_at,
    )


@router.get(
    "/scenarios/{scenario_id}/mechanism/audit",
    response_model=list[MechanismAuditEventResponse],
)
def get_mechanism_audit_events(
    scenario_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _load_scenario(db, scenario_id, current_user)
    scenario_marker = f"scenario={scenario_id}"
    return (
        db.query(AuditLog)
        .filter(
            or_(
                AuditLog.detail.contains(scenario_marker),
                (
                    (AuditLog.resource_type == "scenario")
                    & (AuditLog.resource_id == str(scenario_id))
                ),
            )
        )
        .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .limit(200)
        .all()
    )


@router.get(
    "/scenarios/{scenario_id}/mechanism/material-ledger",
    response_model=list[MaterialLedgerResponse],
)
def get_material_ledger(
    scenario_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _load_scenario(db, scenario_id, current_user)
    return list_material_ledger_entries(db, scenario_id)


@router.put(
    "/scenarios/{scenario_id}/mechanism/material-ledger/{block_id}",
    response_model=MaterialLedgerResponse,
)
def put_material_ledger_entry(
    scenario_id: int,
    block_id: str,
    body: MaterialLedgerUpsertRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    scenario = _load_scenario(db, scenario_id, current_user)
    try:
        entry = upsert_material_ledger_entry(
            db,
            scenario=scenario,
            block_id=block_id,
            request=body,
            user=current_user,
            is_legal=is_legal_role(current_user),
        )
        write_audit_log(
            db,
            user=current_user,
            action="mechanism.material_state",
            resource_type="material_block",
            resource_id=entry.id,
            detail=f"scenario={scenario_id} block={block_id} state={body.state} revision={entry.revision}",
            commit=False,
        )
        db.commit()
        db.refresh(entry)
        return entry
    except (MechanismConflict, MechanismValidationError) as exc:
        db.rollback()
        _raise_service_error(exc)


@router.get(
    "/scenarios/{scenario_id}/mechanism/coverage-tasks",
    response_model=list[CoverageTaskResponse],
)
def get_coverage_tasks(
    scenario_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _load_scenario(db, scenario_id, current_user)
    return [_coverage_task_response(task) for task in list_coverage_tasks(db, scenario_id)]


@router.get(
    "/scenarios/{scenario_id}/mechanism/facts",
    response_model=list[FactRecordResponse],
)
def get_fact_records(
    scenario_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _load_scenario(db, scenario_id, current_user)
    return list_fact_records(db, scenario_id)


@router.post(
    "/scenarios/{scenario_id}/mechanism/facts",
    response_model=FactRecordResponse,
    status_code=status.HTTP_201_CREATED,
)
def post_fact_record(
    scenario_id: int,
    body: FactRecordCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    scenario = _load_scenario(db, scenario_id, current_user)
    try:
        fact = create_fact_record(db, scenario=scenario, request=body, user=current_user)
        write_audit_log(
            db,
            user=current_user,
            action="mechanism.fact_create",
            resource_type="fact",
            resource_id=fact.id,
            detail=f"scenario={scenario_id} block={fact.block_id} status=submitted",
            commit=False,
        )
        db.commit()
        db.refresh(fact)
        return fact
    except MechanismValidationError as exc:
        db.rollback()
        _raise_service_error(exc)


@router.post(
    "/scenarios/{scenario_id}/mechanism/facts/{fact_id}/confirm",
    response_model=FactRecordResponse,
)
def post_confirm_fact_record(
    scenario_id: int,
    fact_id: str,
    body: FactConfirmRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    scenario = _load_scenario(db, scenario_id, current_user)
    fact = db.get(FactRecord, fact_id)
    if fact is None or fact.scenario_id != scenario_id:
        raise HTTPException(status_code=404, detail="事实不存在")
    try:
        fact = confirm_fact_record(
            db,
            fact=fact,
            scenario=scenario,
            confirmation_note=body.confirmation_note,
            user=current_user,
        )
        write_audit_log(
            db,
            user=current_user,
            action="mechanism.fact_business_confirm",
            resource_type="fact",
            resource_id=fact.id,
            detail=f"scenario={scenario_id} block={fact.block_id} status=business_confirmed",
            commit=False,
        )
        db.commit()
        db.refresh(fact)
        return fact
    except (MechanismConflict, MechanismValidationError) as exc:
        db.rollback()
        _raise_service_error(exc)


@router.post(
    "/scenarios/{scenario_id}/mechanism/coverage-tasks",
    response_model=CoverageTaskResponse,
    status_code=status.HTTP_201_CREATED,
)
def post_coverage_task(
    scenario_id: int,
    body: CoverageTaskCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_legal(current_user)
    scenario = _load_scenario(db, scenario_id, current_user)
    try:
        task = create_coverage_task(db, scenario=scenario, request=body, user=current_user)
        write_audit_log(
            db,
            user=current_user,
            action="mechanism.coverage_task_create",
            resource_type="coverage_task",
            resource_id=task.id,
            detail=(
                f"scenario={scenario_id} denominator={len(task.denominator_items)} "
                f"covered={len(task.covered_items)} snapshot={task.denominator_snapshot_hash}"
            ),
            commit=False,
        )
        db.commit()
        db.refresh(task)
        return _coverage_task_response(task)
    except MechanismValidationError as exc:
        db.rollback()
        _raise_service_error(exc)


@router.post(
    "/scenarios/{scenario_id}/mechanism/claims/compile",
    response_model=ClaimCompilationResponse,
    status_code=status.HTTP_201_CREATED,
)
def post_compile_claims(
    scenario_id: int,
    body: ClaimCompileRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_legal(current_user)
    scenario = _load_scenario(db, scenario_id, current_user)
    try:
        compilation, claims = compile_claims(
            db, scenario=scenario, request=body, user=current_user
        )
        write_audit_log(
            db,
            user=current_user,
            action="mechanism.claim_compile",
            resource_type="claim_compilation",
            resource_id=compilation.id,
            detail=(
                f"scenario={scenario_id} denominator={compilation.denominator_count} "
                f"ready={compilation.ready_count} refused={compilation.refused_count} "
                f"input_hash={compilation.input_hash} output_hash={compilation.output_hash}"
            ),
            commit=False,
        )
        db.commit()
        db.refresh(compilation)
        for claim in claims:
            db.refresh(claim)
        return _compilation_response(
            compilation,
            claims,
            compilation_research_items(db, compilation.id),
        )
    except MechanismValidationError as exc:
        db.rollback()
        _raise_service_error(exc)


@router.get(
    "/scenarios/{scenario_id}/mechanism/claims/latest",
    response_model=ClaimCompilationResponse,
)
def get_latest_claims(
    scenario_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _load_scenario(db, scenario_id, current_user)
    result = latest_compilation(db, scenario_id)
    if result is None:
        raise HTTPException(status_code=404, detail="尚无 Claim 编译结果")
    compilation, claims = result
    return _compilation_response(
        compilation,
        claims,
        compilation_research_items(db, compilation.id),
    )


@router.get(
    "/scenarios/{scenario_id}/mechanism/research-items/latest",
    response_model=list[ResearchItemResponse],
)
def get_latest_research_items(
    scenario_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _load_scenario(db, scenario_id, current_user)
    result = latest_compilation(db, scenario_id)
    if result is None:
        raise HTTPException(status_code=404, detail="尚无 ResearchItem 编译结果")
    compilation, _claims = result
    return compilation_research_items(db, compilation.id)


@router.post(
    "/scenarios/{scenario_id}/mechanism/research-items/{item_id}/decision",
    response_model=ResearchItemResponse,
)
def post_research_item_decision(
    scenario_id: int,
    item_id: str,
    body: ResearchItemDecisionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_legal(current_user)
    scenario = _load_scenario(db, scenario_id, current_user)
    item = db.get(ResearchItem, item_id)
    if item is None or item.scenario_id != scenario_id:
        raise HTTPException(status_code=404, detail="ResearchItem 不存在")
    try:
        item = decide_research_item(
            db,
            scenario=scenario,
            item=item,
            request=body,
            user=current_user,
        )
        write_audit_log(
            db,
            user=current_user,
            action="mechanism.research_item_decision",
            resource_type="research_item",
            resource_id=item.id,
            detail=(
                f"scenario={scenario_id} code={item.checklist_code} "
                f"disposition={body.disposition}"
            ),
            commit=False,
        )
        db.commit()
        db.refresh(item)
        return item
    except (MechanismConflict, MechanismValidationError) as exc:
        db.rollback()
        _raise_service_error(exc)


@router.post(
    "/scenarios/{scenario_id}/mechanism/claims/{claim_id}/confirm",
    response_model=ClaimRecordResponse,
)
def post_confirm_claim(
    scenario_id: int,
    claim_id: str,
    body: ClaimConfirmRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_legal(current_user)
    _load_scenario(db, scenario_id, current_user)
    claim = db.get(ClaimRecord, claim_id)
    if claim is None or claim.scenario_id != scenario_id:
        raise HTTPException(status_code=404, detail="Claim 不存在")
    try:
        claim = confirm_claim(
            db,
            claim=claim,
            decision=body.decision,
            confirmation_note=body.confirmation_note,
            user=current_user,
        )
        write_audit_log(
            db,
            user=current_user,
            action="mechanism.claim_human_decision",
            resource_type="claim",
            resource_id=claim.id,
            detail=f"scenario={scenario_id} decision={body.decision} code={claim.checklist_code}",
            commit=False,
        )
        db.commit()
        db.refresh(claim)
        return claim
    except MechanismConflict as exc:
        db.rollback()
        _raise_service_error(exc)


@router.post(
    "/scenarios/{scenario_id}/mechanism/coverage-proofs",
    response_model=CoverageProofResponse,
    status_code=status.HTTP_201_CREATED,
)
def post_coverage_proof(
    scenario_id: int,
    body: CoverageProofCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_legal(current_user)
    scenario = _load_scenario(db, scenario_id, current_user)
    if body.compilation_id:
        compilation = db.get(ClaimCompilation, body.compilation_id)
        if compilation is None or compilation.scenario_id != scenario_id:
            raise HTTPException(status_code=404, detail="Claim compilation 不存在")
        claims = compilation_claims(db, compilation.id)
    else:
        result = latest_compilation(db, scenario_id)
        if result is None:
            raise HTTPException(status_code=409, detail="请先编译 Claim")
        compilation, claims = result
    try:
        proof = create_coverage_proof(
            db,
            scenario=scenario,
            compilation=compilation,
            claims=claims,
            denominator_ref=body.denominator_ref,
            user=current_user,
        )
    except MechanismValidationError as exc:
        db.rollback()
        _raise_service_error(exc)
    write_audit_log(
        db,
        user=current_user,
        action="mechanism.coverage_proof_create",
        resource_type="coverage_proof",
        resource_id=proof.id,
        detail=(
            f"scenario={scenario_id} covered={proof.covered_count}/{proof.denominator_count} "
            f"unanswerable={proof.unanswerable_count} proof_hash={proof.proof_hash}"
        ),
        commit=False,
    )
    db.commit()
    db.refresh(proof)
    return proof


@router.get(
    "/scenarios/{scenario_id}/mechanism/coverage-proofs/latest",
    response_model=CoverageProofResponse,
)
def get_latest_coverage_proof(
    scenario_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _load_scenario(db, scenario_id, current_user)
    proof = latest_coverage_proof(db, scenario_id)
    if proof is None:
        raise HTTPException(status_code=404, detail="尚无覆盖证明")
    return proof
