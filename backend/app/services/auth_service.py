from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import get_settings, is_instance_organization_member
from app.core.security import create_access_token, get_password_hash, verify_password
from app.core.roles import ROLE_BUSINESS
from app.models.user import User
from app.schemas.auth import UserRegister
from app.services.audit import write_audit_log


_DUMMY_PASSWORD_HASH = get_password_hash("Vela-Dummy-Password-Only-For-Timing-2026!")


def register_user(db: Session, payload: UserRegister) -> User:
    settings = get_settings()
    if not settings.allow_open_registration:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="当前环境已关闭开放注册，请联系部署管理员开通账户",
        )
    if not payload.accept_disclaimer:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="注册须勾选同意免责声明与数据使用条款",
        )

    existing = db.query(User).filter(User.email == payload.email).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="该邮箱已注册")

    now = datetime.now(timezone.utc)
    user = User(
        email=payload.email.lower(),
        full_name=payload.full_name,
        organization=payload.organization,
        hashed_password=get_password_hash(payload.password),
        role=ROLE_BUSINESS,
        auth_provider="local",
        disclaimer_accepted=True,
        disclaimer_accepted_at=now,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    write_audit_log(
        db,
        user=user,
        action="user.register",
        detail=f"开放注册（{ROLE_BUSINESS}）并完成免责条款确认",
    )
    return user


def authenticate_user(db: Session, email: str, password: str) -> User:
    settings = get_settings()
    if not settings.allow_password_login and settings.sso_configured:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="当前环境已启用 SSO，请使用企业单点登录",
        )
    user = db.query(User).filter(User.email == email.lower()).first()
    candidate_hash = user.hashed_password if user and user.hashed_password else _DUMMY_PASSWORD_HASH
    try:
        password_valid = verify_password(password, candidate_hash)
    except (TypeError, ValueError):
        password_valid = False
    if user is None or not user.hashed_password or not password_valid:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="邮箱或密码错误")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="账户已停用")
    if not is_instance_organization_member(user.organization, settings):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="该账户不属于此受控试点实例",
        )
    return user


def login_user(db: Session, user: User) -> str:
    write_audit_log(db, user=user, action="user.login")
    return create_access_token(subject=user.email)


def accept_disclaimer(db: Session, user: User) -> User:
    if user.disclaimer_accepted:
        return user

    user.disclaimer_accepted = True
    user.disclaimer_accepted_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(user)
    write_audit_log(db, user=user, action="user.accept_disclaimer")
    return user
