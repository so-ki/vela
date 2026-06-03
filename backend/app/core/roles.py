"""Role definitions and permission helpers."""

from __future__ import annotations

from typing import Iterable

from app.models.user import User

ROLE_BUSINESS = "business"
ROLE_LEGAL = "legal"
ROLE_ADMIN = "admin"

ROLE_LABELS: dict[str, str] = {
    ROLE_BUSINESS: "业务协同",
    ROLE_LEGAL: "法务复核",
    ROLE_ADMIN: "系统管理员",
}


def role_label(role: str) -> str:
    return ROLE_LABELS.get(role, role)


def is_legal_role(user: User) -> bool:
    return user.role in (ROLE_LEGAL, ROLE_ADMIN)


def is_business_role(user: User) -> bool:
    return user.role == ROLE_BUSINESS


def require_role(user: User, allowed: Iterable[str]) -> None:
    from fastapi import HTTPException, status

    if user.role not in allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"当前角色（{role_label(user.role)}）无权执行此操作",
        )
