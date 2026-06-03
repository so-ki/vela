from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlencode

import httpx
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.roles import ROLE_BUSINESS, ROLE_LEGAL
from app.core.security import create_access_token, get_password_hash
from app.models.user import User
from app.services.audit import write_audit_log
from app.services.auth_service import login_user


def sso_public_config() -> dict[str, Any]:
    settings = get_settings()
    return {
        "enabled": settings.sso_configured,
        "provider_name": settings.sso_provider_name,
        "allow_password_login": settings.allow_password_login or not settings.sso_configured,
        "allow_open_registration": settings.allow_open_registration,
    }


async def _fetch_oidc_metadata(issuer_url: str) -> dict[str, Any]:
    base = issuer_url.rstrip("/")
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(f"{base}/.well-known/openid-configuration")
        resp.raise_for_status()
        return resp.json()


async def build_sso_login_url(state: str) -> str:
    settings = get_settings()
    if not settings.sso_configured:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="SSO 未配置")
    metadata = await _fetch_oidc_metadata(settings.sso_issuer_url)
    params = {
        "client_id": settings.sso_client_id,
        "response_type": "code",
        "scope": settings.sso_scopes,
        "redirect_uri": settings.sso_redirect_uri,
        "state": state,
    }
    return f"{metadata['authorization_endpoint']}?{urlencode(params)}"


def _resolve_role(raw_groups: list[str] | None) -> str:
    settings = get_settings()
    default = settings.sso_default_role if settings.sso_default_role in ("legal", "business", "admin") else ROLE_LEGAL
    if not raw_groups:
        return default
    lowered = [g.lower() for g in raw_groups]
    if any("admin" in g for g in lowered):
        return "admin"
    if any("legal" in g or "法务" in g for g in lowered):
        return ROLE_LEGAL
    if any("business" in g or "业务" in g for g in lowered):
        return ROLE_BUSINESS
    return default


def _get_or_create_sso_user(db: Session, *, email: str, full_name: str, subject: str, groups: list[str] | None) -> User:
    settings = get_settings()
    email = email.lower()
    user = db.query(User).filter(User.email == email).first()
    if user is None:
        if not settings.sso_jit_provision:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="SSO 用户未预授权，请联系管理员")
        user = User(
            email=email,
            full_name=full_name or email.split("@")[0],
            organization=None,
            hashed_password=get_password_hash(secrets.token_urlsafe(32)),
            role=_resolve_role(groups),
            auth_provider="sso",
            external_subject=subject,
            disclaimer_accepted=True,
            disclaimer_accepted_at=datetime.now(timezone.utc),
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        write_audit_log(db, user=user, action="user.sso_provision", detail=f"JIT provision via SSO ({subject})")
        return user

    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="账户已停用")
    user.auth_provider = user.auth_provider or "sso"
    user.external_subject = subject
    if not user.full_name and full_name:
        user.full_name = full_name
    db.commit()
    db.refresh(user)
    return user


async def exchange_sso_code(db: Session, code: str) -> tuple[str, User]:
    settings = get_settings()
    if not settings.sso_configured:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="SSO 未配置")

    metadata = await _fetch_oidc_metadata(settings.sso_issuer_url)
    token_endpoint = metadata["token_endpoint"]
    userinfo_endpoint = metadata.get("userinfo_endpoint")

    async with httpx.AsyncClient(timeout=20.0) as client:
        token_resp = await client.post(
            token_endpoint,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": settings.sso_redirect_uri,
                "client_id": settings.sso_client_id,
                "client_secret": settings.sso_client_secret,
            },
            headers={"Accept": "application/json"},
        )
        if token_resp.status_code >= 400:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="SSO 令牌交换失败")
        token_data = token_resp.json()
        access_token = token_data.get("access_token")
        id_token_claims = token_data.get("id_token")
        email = token_data.get("email")
        name = token_data.get("name")
        subject = token_data.get("sub")

        if userinfo_endpoint and access_token:
            ui = await client.get(userinfo_endpoint, headers={"Authorization": f"Bearer {access_token}"})
            if ui.status_code < 400:
                info = ui.json()
                email = info.get("email") or email
                name = info.get("name") or info.get("preferred_username") or name
                subject = info.get("sub") or subject

    if not email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="SSO 未返回 email，无法映射本地账户")

    groups = None
    user = _get_or_create_sso_user(
        db,
        email=email,
        full_name=name or "",
        subject=subject or email,
        groups=groups,
    )
    jwt = login_user(db, user)
    write_audit_log(db, user=user, action="user.sso_login", detail=f"provider={settings.sso_provider_name}")
    return jwt, user
