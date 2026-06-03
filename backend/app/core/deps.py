from __future__ import annotations

from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import decode_access_token
from app.core.roles import ROLE_ADMIN, ROLE_BUSINESS, ROLE_LEGAL, require_role
from app.models.user import User

bearer_scheme = HTTPBearer(auto_error=False)


def _resolve_user(
    credentials: Optional[HTTPAuthorizationCredentials],
    db: Session,
) -> User:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未登录或令牌无效")

    email = decode_access_token(credentials.credentials)
    if email is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="登录已过期，请重新登录")

    user = db.query(User).filter(User.email == email).first()
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户不存在或已停用")

    return user


def get_authenticated_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    return _resolve_user(credentials, db)


def get_current_user(user: User = Depends(get_authenticated_user)) -> User:
    if not user.disclaimer_accepted:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="请先阅读并同意免责声明与数据使用条款",
        )
    return user


def get_current_legal_user(user: User = Depends(get_current_user)) -> User:
    require_role(user, (ROLE_LEGAL, ROLE_ADMIN))
    return user


def get_current_business_user(user: User = Depends(get_current_user)) -> User:
    require_role(user, (ROLE_BUSINESS,))
    return user
