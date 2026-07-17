from __future__ import annotations

import secrets
import hashlib
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlencode

import httpx
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.roles import ROLE_ADMIN, ROLE_BUSINESS, ROLE_LEGAL
from app.core.security import get_password_hash
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
    groups = {str(group).strip().casefold() for group in (raw_groups or []) if str(group).strip()}

    def configured(value: str) -> set[str]:
        return {item.strip().casefold() for item in value.split(",") if item.strip()}

    # Privileged roles require an exact, explicitly configured group match.
    # Substring checks such as "admin-ish" or "LegalOps" are intentionally
    # rejected because they turn IdP naming accidents into global privilege.
    if groups & configured(settings.sso_admin_groups):
        return ROLE_ADMIN
    if groups & configured(settings.sso_legal_groups):
        return ROLE_LEGAL
    if groups & configured(settings.sso_business_groups):
        return ROLE_BUSINESS
    return ROLE_BUSINESS


def _get_or_create_sso_user(
    db: Session,
    *,
    email: str,
    full_name: str,
    issuer: str,
    subject: str,
    groups: list[str] | None,
) -> User:
    settings = get_settings()
    email = email.lower()
    if not subject:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="SSO 未返回稳定 subject")
    binding = "oidc:" + hashlib.sha256(f"{issuer.rstrip('/')}|{subject}".encode("utf-8")).hexdigest()
    bound_user = db.query(User).filter(User.external_subject == binding).first()
    email_user = db.query(User).filter(User.email == email).first()
    if bound_user is not None and bound_user.email != email:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="SSO 身份绑定与邮箱不一致，请联系管理员")
    if email_user is not None and bound_user is not None and email_user.id != bound_user.id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="SSO 身份与现有账户冲突")
    user = bound_user or email_user
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
            external_subject=binding,
            disclaimer_accepted=True,
            disclaimer_accepted_at=datetime.now(timezone.utc),
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        write_audit_log(db, user=user, action="user.sso_provision", detail="JIT provision via verified SSO")
        return user

    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="账户已停用")
    if user.auth_provider != "sso":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="该邮箱已绑定非 SSO 账户，禁止自动接管，请联系管理员",
        )
    if user.external_subject and user.external_subject != binding:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="SSO subject 与账户永久绑定不一致")
    user.external_subject = binding
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
        email = token_data.get("email")
        name = token_data.get("name")
        subject = token_data.get("sub")
        groups: list[str] = []
        email_verified: Any = token_data.get("email_verified")

        if userinfo_endpoint and access_token:
            ui = await client.get(userinfo_endpoint, headers={"Authorization": f"Bearer {access_token}"})
            if ui.status_code < 400:
                info = ui.json()
                email = info.get("email") or email
                name = info.get("name") or info.get("preferred_username") or name
                subject = info.get("sub") or subject
                email_verified = info.get("email_verified", email_verified)
                raw_groups = info.get(settings.sso_groups_claim, [])
                if isinstance(raw_groups, list):
                    groups = [str(group) for group in raw_groups]
                elif isinstance(raw_groups, str):
                    groups = [raw_groups]

    if not email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="SSO 未返回 email，无法映射本地账户")
    if settings.sso_require_verified_email and email_verified is not True:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="SSO 邮箱未通过 IdP 验证")
    if not subject:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="SSO 未返回稳定 subject")

    user = _get_or_create_sso_user(
        db,
        email=email,
        full_name=name or "",
        issuer=settings.sso_issuer_url,
        subject=subject,
        groups=groups,
    )
    jwt = login_user(db, user)
    write_audit_log(db, user=user, action="user.sso_login", detail=f"provider={settings.sso_provider_name}")
    return jwt, user
