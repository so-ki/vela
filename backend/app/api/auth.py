from __future__ import annotations

import secrets
import time
from typing import Optional
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.deps import get_authenticated_user, get_current_user
from app.models.user import User
from app.schemas.auth import AcceptDisclaimerRequest, SsoConfigResponse, TokenResponse, UserLogin, UserRegister, UserResponse
from app.services.auth_service import accept_disclaimer, authenticate_user, login_user, register_user
from app.services.disclaimer import DISCLAIMER_FULL_TEXT, DISCLAIMER_SECTIONS, DISCLAIMER_TITLE, DISCLAIMER_VERSION
from app.services.sso_service import build_sso_login_url, exchange_sso_code, sso_public_config

router = APIRouter(prefix="/auth", tags=["认证"])

_SSO_STATE_TTL_SECONDS = 600
_SSO_STATE_MAX_ENTRIES = 10_000
_SSO_STATES: dict[str, float] = {}


@router.get("/disclaimer")
def get_disclaimer():
    return {
        "title": DISCLAIMER_TITLE,
        "version": DISCLAIMER_VERSION,
        "sections": DISCLAIMER_SECTIONS,
        "full_text": DISCLAIMER_FULL_TEXT,
    }


@router.get("/sso/config", response_model=SsoConfigResponse)
def sso_config():
    return SsoConfigResponse(**sso_public_config())


@router.get("/sso/login")
async def sso_login():
    if not get_settings().sso_configured:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="SSO 未配置")
    now = time.monotonic()
    for existing, expires_at in list(_SSO_STATES.items()):
        if expires_at <= now:
            _SSO_STATES.pop(existing, None)
    while len(_SSO_STATES) >= _SSO_STATE_MAX_ENTRIES:
        _SSO_STATES.pop(next(iter(_SSO_STATES)))
    state = secrets.token_urlsafe(24)
    _SSO_STATES[state] = now + _SSO_STATE_TTL_SECONDS
    url = await build_sso_login_url(state)
    return RedirectResponse(url)


@router.get("/sso/callback")
async def sso_callback(
    code: Optional[str] = Query(default=None),
    state: Optional[str] = Query(default=None),
    error: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
):
    settings = get_settings()
    if error:
        target = f"{settings.frontend_url}/login?{urlencode({'sso_error': error})}"
        return RedirectResponse(target)
    expires_at = _SSO_STATES.pop(state, None) if state else None
    if not code or expires_at is None or expires_at <= time.monotonic():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="无效的 SSO 回调参数")

    token, user = await exchange_sso_code(db, code)
    params = urlencode(
        {
            "access_token": token,
            "email": user.email,
            "full_name": user.full_name,
            "role": user.role,
            "disclaimer_accepted": str(user.disclaimer_accepted).lower(),
        }
    )
    return RedirectResponse(f"{settings.frontend_url}/login/sso/callback?{params}")


@router.post("/register", response_model=UserResponse, status_code=201)
def register(payload: UserRegister, db: Session = Depends(get_db)):
    return register_user(db, payload)


@router.post("/login", response_model=TokenResponse)
def login(payload: UserLogin, response: Response, db: Session = Depends(get_db)):
    user = authenticate_user(db, payload.email, payload.password)
    token = login_user(db, user)
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    return TokenResponse(access_token=token, user=UserResponse.model_validate(user))


@router.post("/accept-disclaimer", response_model=UserResponse)
def accept_disclaimer_endpoint(
    payload: AcceptDisclaimerRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_authenticated_user),
):
    if not payload.accept:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="须明确同意条款方可继续")
    return accept_disclaimer(db, current_user)


@router.get("/me", response_model=UserResponse)
def me(current_user: User = Depends(get_authenticated_user)):
    return current_user


@router.get("/preferences")
def user_preferences(current_user: User = Depends(get_current_user)):
    from app.services.user_preference_service import preference_summary

    return preference_summary(current_user.id)


class RetrievalPreferencesUpdate(BaseModel):
    match_threshold: Optional[int] = Field(default=None, ge=50, le=95)
    retrieval_top_k: Optional[int] = Field(default=None, ge=1, le=10)


@router.put("/preferences/retrieval")
def update_retrieval_preferences(
    body: RetrievalPreferencesUpdate,
    current_user: User = Depends(get_current_user),
):
    from app.services.user_preference_service import (
        preference_summary,
        record_match_threshold_choice,
        record_retrieval_top_k_choice,
    )

    if body.match_threshold is not None:
        record_match_threshold_choice(current_user.id, body.match_threshold)
    if body.retrieval_top_k is not None:
        record_retrieval_top_k_choice(current_user.id, body.retrieval_top_k)
    return preference_summary(current_user.id)
