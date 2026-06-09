from __future__ import annotations

from typing import Optional

import copy

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.orm.attributes import flag_modified

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.scenario import InvestigationScenario
from app.models.user import User
from app.schemas.onboarding import ProjectHubResponse
from app.services.audit import write_audit_log
from app.services.contract_review_service import (
    analyze_contract,
    get_contract_analysis,
    review_contract_finding,
    upload_contract_document,
)
from app.services.diligence_service import run_diligence_analysis, upload_diligence_document
from app.services.project_hub_service import (
    ensure_project_hub,
    hub_summary,
    project_context as build_project_context,
)
from app.services.project_intelligence_service import run_project_intelligence

router = APIRouter(prefix="/projects", tags=["项目中心"])


class ContractFindingReviewRequest(BaseModel):
    clause_index: int = Field(..., ge=1)
    decision: str = Field(..., pattern="^(confirmed|false_positive)$")
    comment: Optional[str] = None


def _load_scenario(db: Session, project_id: int, user: User) -> InvestigationScenario:
    scenario = (
        db.query(InvestigationScenario)
        .options(joinedload(InvestigationScenario.checklist))
        .filter(InvestigationScenario.id == project_id)
        .first()
    )
    if not scenario or not scenario.checklist:
        raise HTTPException(status_code=404, detail="项目不存在")
    if scenario.user_id != user.id and user.role not in ("legal", "admin"):
        raise HTTPException(status_code=403, detail="无权访问该项目")
    return scenario


def _save_payload(db: Session, scenario: InvestigationScenario, payload: dict) -> None:
    scenario.checklist.payload = copy.deepcopy(payload)
    flag_modified(scenario.checklist, "payload")
    db.commit()


@router.get("/{project_id}/hub", response_model=ProjectHubResponse)
def get_project_hub(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    scenario = _load_scenario(db, project_id, current_user)
    payload = ensure_project_hub(scenario.checklist.payload)
    _save_payload(db, scenario, payload)
    summary = hub_summary(payload, scenario)
    return ProjectHubResponse(**summary)


@router.get("/{project_id}/context")
def get_project_context_api(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    scenario = _load_scenario(db, project_id, current_user)
    payload = ensure_project_hub(scenario.checklist.payload)
    return build_project_context(payload, scenario)


@router.post("/{project_id}/contracts/upload")
async def upload_contract(
    project_id: int,
    contract_type: str = "general",
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    scenario = _load_scenario(db, project_id, current_user)
    content = await file.read()
    payload = ensure_project_hub(scenario.checklist.payload)
    doc = upload_contract_document(
        payload,
        filename=file.filename or "contract.pdf",
        content=content,
        contract_type=contract_type,
    )
    _save_payload(db, scenario, payload)
    write_audit_log(
        db,
        user=current_user,
        action="contract_upload",
        resource_type="project",
        resource_id=str(project_id),
        detail=f"doc_id={doc['id']}",
    )
    return doc


@router.post("/{project_id}/contracts/analyze")
def analyze_project_contract(
    project_id: int,
    doc_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    scenario = _load_scenario(db, project_id, current_user)
    payload = scenario.checklist.payload
    try:
        result = analyze_contract(payload, scenario, doc_id=doc_id, user_id=current_user.id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _save_payload(db, scenario, payload)
    write_audit_log(
        db,
        user=current_user,
        action="contract_analyze",
        resource_type="project",
        resource_id=str(project_id),
        detail=f"doc_id={doc_id}",
    )
    return result


@router.get("/{project_id}/contracts/{doc_id}")
def get_project_contract_analysis(
    project_id: int,
    doc_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    scenario = _load_scenario(db, project_id, current_user)
    try:
        return get_contract_analysis(scenario.checklist.payload, doc_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{project_id}/contracts/{doc_id}/findings/review")
def review_project_contract_finding(
    project_id: int,
    doc_id: str,
    body: ContractFindingReviewRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    scenario = _load_scenario(db, project_id, current_user)
    if current_user.role not in ("legal", "admin"):
        raise HTTPException(status_code=403, detail="仅法务可确认合同条款审查结果")
    payload = scenario.checklist.payload
    try:
        finding = review_contract_finding(
            payload,
            doc_id=doc_id,
            clause_index=body.clause_index,
            decision=body.decision,
            user_id=current_user.id,
            comment=body.comment,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _save_payload(db, scenario, payload)
    write_audit_log(
        db,
        user=current_user,
        action="contract_finding_review",
        resource_type="project",
        resource_id=str(project_id),
        detail=f"doc={doc_id} clause={body.clause_index} decision={body.decision}",
    )
    return finding


@router.post("/{project_id}/diligence/upload")
async def upload_diligence_doc(
    project_id: int,
    doc_category: Optional[str] = None,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    scenario = _load_scenario(db, project_id, current_user)
    content = await file.read()
    payload = ensure_project_hub(scenario.checklist.payload)
    doc = upload_diligence_document(
        payload,
        filename=file.filename or "dd_doc.pdf",
        content=content,
        doc_category=doc_category,
    )
    _save_payload(db, scenario, payload)
    write_audit_log(
        db,
        user=current_user,
        action="diligence_upload",
        resource_type="project",
        resource_id=str(project_id),
        detail=f"doc_id={doc['id']}",
    )
    return doc


@router.post("/{project_id}/diligence/analyze")
def analyze_project_diligence(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    scenario = _load_scenario(db, project_id, current_user)
    payload = scenario.checklist.payload
    result = run_diligence_analysis(payload, scenario, user_id=current_user.id)
    _save_payload(db, scenario, payload)
    write_audit_log(
        db,
        user=current_user,
        action="diligence_analyze",
        resource_type="project",
        resource_id=str(project_id),
    )
    return result


@router.get("/{project_id}/intelligence/report")
def get_intelligence_report(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    scenario = _load_scenario(db, project_id, current_user)
    report = scenario.checklist.payload.get("project_intelligence")
    if not report:
        raise HTTPException(status_code=404, detail="尚未运行项目统摄分析")
    return report


@router.post("/{project_id}/intelligence/run")
def run_intelligence(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    scenario = _load_scenario(db, project_id, current_user)
    payload = ensure_project_hub(scenario.checklist.payload)
    report = run_project_intelligence(payload, scenario, user_id=current_user.id)
    _save_payload(db, scenario, payload)
    write_audit_log(
        db,
        user=current_user,
        action="project_intelligence",
        resource_type="project",
        resource_id=str(project_id),
        detail=f"issues={report.get('issue_count')} high={report.get('high_count')}",
    )
    return report


@router.get("/{project_id}/diligence/report")
def get_diligence_report(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    scenario = _load_scenario(db, project_id, current_user)
    report = scenario.checklist.payload.get("diligence_report")
    if not report:
        raise HTTPException(status_code=404, detail="尚未运行尽调分析")
    return report
