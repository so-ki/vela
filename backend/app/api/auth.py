from __future__ import annotations

import secrets
from typing import Optional
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
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
    state = secrets.token_urlsafe(24)
    _SSO_STATES[state] = 1.0
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
        target = f"{settings.frontend_url}/login?sso_error={error}"
        return RedirectResponse(target)
    if not code or not state or state not in _SSO_STATES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="无效的 SSO 回调参数")
    _SSO_STATES.pop(state, None)

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
def login(payload: UserLogin, db: Session = Depends(get_db)):
    user = authenticate_user(db, payload.email, payload.password)
    token = login_user(db, user)
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
