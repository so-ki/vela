from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status

from app.core.deps import get_current_legal_user, get_current_user
from app.core.roles import ROLE_ADMIN, ROLE_BUSINESS, ROLE_LEGAL, require_role
from app.models.user import User
from app.schemas.onboarding import (
    InterviewAnswerRequest,
    InterviewCompleteRequest,
    InterviewStartResponse,
    OnboardingStatusResponse,
    PlaybookProfileResponse,
)
from app.services.cold_start_service import (
    complete_interview,
    get_playbook_profile,
    is_onboarding_complete,
    load_interview_script,
    save_playbook_template,
    start_interview,
    submit_interview_answer,
    sync_interview_answers,
    upload_interview_attachment,
)

router = APIRouter(prefix="/onboarding", tags=["冷启动与 Playbook"])


@router.get("/interview/script")
def interview_script(_: User = Depends(get_current_legal_user)):
    return load_interview_script()


@router.get("/profile", response_model=PlaybookProfileResponse)
def playbook_profile(current_user: User = Depends(get_current_legal_user)):
    p = get_playbook_profile(
        current_user.id,
        owner_email=current_user.email,
        owner_auth_provider=current_user.auth_provider,
        owner_external_subject=current_user.external_subject,
    )
    return PlaybookProfileResponse(
        completed=bool(p.get("completed")),
        user_id=p.get("user_id", current_user.id),
        profile_schema_version=p.get("profile_schema_version"),
        profile_version=p.get("profile_version"),
        profile_source=p.get("profile_source"),
        completed_at=p.get("completed_at"),
        org_name=p.get("org_name"),
        primary_jurisdiction=p.get("primary_jurisdiction"),
        industry_focus=p.get("industry_focus") or [],
        default_compliance_dimensions=p.get("default_compliance_dimensions") or [],
        suggested_checklist_codes=p.get("suggested_checklist_codes") or [],
        output_language=p.get("output_language"),
        risk_tolerance=p.get("risk_tolerance"),
        match_threshold_adjustment=int(p.get("match_threshold_adjustment") or 0),
        contract_house_rules=p.get("contract_house_rules"),
        brief_template_style=p.get("brief_template_style"),
        external_counsel_triggers=p.get("external_counsel_triggers"),
        playbook_md=p.get("playbook_md"),
        message=p.get("message"),
    )


@router.get("/status", response_model=OnboardingStatusResponse)
def onboarding_status(current_user: User = Depends(get_current_user)):
    if current_user.role == ROLE_BUSINESS:
        return OnboardingStatusResponse(completed=True, required=False, role=current_user.role)
    require_role(current_user, (ROLE_LEGAL, ROLE_ADMIN))
    return OnboardingStatusResponse(
        completed=is_onboarding_complete(
            current_user.id,
            owner_email=current_user.email,
            owner_auth_provider=current_user.auth_provider,
            owner_external_subject=current_user.external_subject,
        ),
        required=True,
        role=current_user.role,
    )


@router.post("/interview/start", response_model=InterviewStartResponse)
def interview_start(current_user: User = Depends(get_current_legal_user)):
    result = start_interview(current_user.id)
    return InterviewStartResponse(**result)


@router.post("/interview/{session_id}/answer")
def interview_answer(
    session_id: str,
    body: InterviewAnswerRequest,
    current_user: User = Depends(get_current_legal_user),
):
    try:
        return submit_interview_answer(session_id, current_user.id, body.question_id, body.answer)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/interview/{session_id}/sync")
def interview_sync(
    session_id: str,
    body: dict[str, Any],
    current_user: User = Depends(get_current_legal_user),
):
    answers = body.get("answers") or {}
    try:
        return sync_interview_answers(session_id, current_user.id, answers)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/interview/{session_id}/upload")
async def interview_upload(
    session_id: str,
    file: UploadFile = File(...),
    purpose: str = Query(default="general"),
    parse: bool = Query(default=True),
    parse_into: Optional[str] = Query(default=None),
    merge_mode: str = Query(default="append"),
    current_user: User = Depends(get_current_legal_user),
):
    content = await file.read()
    if len(content) < 10:
        raise HTTPException(status_code=400, detail="文件过短或为空")
    try:
        return upload_interview_attachment(
            session_id,
            current_user.id,
            purpose=purpose,
            filename=file.filename or "upload.bin",
            content=content,
            parse=parse,
            parse_into=parse_into,
            merge_mode=merge_mode,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/interview/complete", response_model=PlaybookProfileResponse)
def interview_complete(body: InterviewCompleteRequest, current_user: User = Depends(get_current_legal_user)):
    try:
        profile = complete_interview(
            body.session_id,
            current_user.id,
            owner_email=current_user.email,
            owner_auth_provider=current_user.auth_provider,
            owner_external_subject=current_user.external_subject,
        )
        return PlaybookProfileResponse(
            completed=True,
            user_id=current_user.id,
            profile_schema_version=profile.get("profile_schema_version"),
            profile_version=profile.get("profile_version"),
            profile_source=profile.get("profile_source"),
            completed_at=profile.get("completed_at"),
            org_name=profile.get("org_name"),
            primary_jurisdiction=profile.get("primary_jurisdiction"),
            industry_focus=profile.get("industry_focus") or [],
            default_compliance_dimensions=profile.get("default_compliance_dimensions") or [],
            suggested_checklist_codes=profile.get("suggested_checklist_codes") or [],
            output_language=profile.get("output_language"),
            risk_tolerance=profile.get("risk_tolerance"),
            match_threshold_adjustment=profile.get("match_threshold_adjustment", 0),
            contract_house_rules=profile.get("contract_house_rules"),
            brief_template_style=profile.get("brief_template_style"),
            external_counsel_triggers=profile.get("external_counsel_triggers"),
            playbook_md=profile.get("playbook_md"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/templates")
async def upload_template(
    file: UploadFile = File(...),
    session_id: Optional[str] = None,
    current_user: User = Depends(get_current_legal_user),
):
    content = await file.read()
    if len(content) < 20:
        raise HTTPException(status_code=400, detail="模板文件过短")
    meta = save_playbook_template(
        current_user.id,
        session_id=session_id,
        filename=file.filename or "template.docx",
        content=content,
        purpose="general",
    )
    return meta
