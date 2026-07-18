from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.roles import is_legal_role
from app.models.legal_source_version import LegalChangeEvent, LegalSourceVersion
from app.models.user import User
from app.schemas.legal_source_version import (
    LegalChangeEventResponse,
    LegalSourceCandidateCreateRequest,
    LegalSourceCandidateResponse,
    LegalSourceDecisionRequest,
    LegalSourceVersionResponse,
    SourceVersionStatus,
)
from app.services.audit import write_audit_log
from app.services.legal_source_version_service import (
    SourceVersionConflict,
    SourceVersionPermissionError,
    SourceVersionValidationError,
    create_source_candidate,
    decide_source_version,
    list_change_events,
    list_source_versions,
)


router = APIRouter(prefix="/legal", tags=["法规变化候选"])


def _require_legal(user: User) -> None:
    if not is_legal_role(user):
        raise HTTPException(status_code=403, detail="法规来源版本的写操作必须由法务人工执行")


def _version_or_404(db: Session, version_id: str) -> LegalSourceVersion:
    version = db.get(LegalSourceVersion, version_id)
    if version is None:
        raise HTTPException(status_code=404, detail="法规来源版本不存在")
    return version


def _event_or_404(db: Session, event_id: str) -> LegalChangeEvent:
    event = db.get(LegalChangeEvent, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="法规变化事件不存在")
    return event


def _service_error(exc: Exception) -> None:
    if isinstance(exc, SourceVersionPermissionError):
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if isinstance(exc, SourceVersionConflict):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post(
    "/source-versions/candidates",
    response_model=LegalSourceCandidateResponse,
    status_code=status.HTTP_201_CREATED,
)
def post_source_candidate(
    body: LegalSourceCandidateCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_legal(current_user)
    try:
        version, event = create_source_candidate(db, request=body, user=current_user)
        write_audit_log(
            db,
            user=current_user,
            action="legal_source.candidate_create",
            resource_type="legal_source_version",
            resource_id=version.id,
            detail=(
                f"canonical_id={version.canonical_id} citation_id={version.citation_id} "
                f"status=candidate raw_hash={version.raw_hash} "
                f"normalized_hash={version.normalized_hash} event={event.id} "
                "release_scope=source_registry_only capability_pack_corpus_updated=false"
            ),
            commit=False,
        )
        db.commit()
        db.refresh(version)
        db.refresh(event)
        return LegalSourceCandidateResponse(version=version, change_event=event)
    except (SourceVersionConflict, SourceVersionPermissionError, SourceVersionValidationError) as exc:
        db.rollback()
        _service_error(exc)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="法规来源版本发生唯一性冲突") from exc


@router.get("/source-versions", response_model=list[LegalSourceVersionResponse])
def get_source_versions(
    canonical_id: Optional[str] = Query(default=None, max_length=512),
    version_status: Optional[SourceVersionStatus] = Query(default=None, alias="status"),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    return list_source_versions(
        db, canonical_id=canonical_id, status=version_status, limit=limit
    )


@router.get("/source-versions/{version_id}", response_model=LegalSourceVersionResponse)
def get_source_version(
    version_id: str,
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    return _version_or_404(db, version_id)


@router.post(
    "/source-versions/{version_id}/decisions",
    response_model=LegalSourceVersionResponse,
)
def post_source_version_decision(
    version_id: str,
    body: LegalSourceDecisionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_legal(current_user)
    version = _version_or_404(db, version_id)
    before = version.status
    try:
        version = decide_source_version(db, version=version, request=body, user=current_user)
        write_audit_log(
            db,
            user=current_user,
            action="legal_source.review_decision",
            resource_type="legal_source_version",
            resource_id=version.id,
            detail=(
                f"canonical_id={version.canonical_id} from={before} to={version.status} "
                "release_scope=source_registry_only capability_pack_corpus_updated=false"
            ),
            commit=False,
        )
        db.commit()
        db.refresh(version)
        return version
    except (
        SourceVersionConflict,
        SourceVersionPermissionError,
        SourceVersionValidationError,
    ) as exc:
        db.rollback()
        _service_error(exc)


@router.get("/change-events", response_model=list[LegalChangeEventResponse])
def get_change_events(
    canonical_id: Optional[str] = Query(default=None, max_length=512),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    return list_change_events(db, canonical_id=canonical_id, limit=limit)


@router.get("/change-events/{event_id}", response_model=LegalChangeEventResponse)
def get_change_event(
    event_id: str,
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    return _event_or_404(db, event_id)
