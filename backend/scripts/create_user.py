#!/usr/bin/env python3
"""Interactively provision one local user for an isolated production deployment.

The command deliberately accepts no password argument or environment variable,
so a credential is not left in shell history, Compose configuration, or process
listings.  Run it from an already-started backend container.
"""

from __future__ import annotations

import argparse
import getpass
import os
import re
import sys
from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_ROOT))

from scripts.container_entrypoint import configure_database_url

ALLOWED_ROLES = ("business", "legal", "admin")
COMMON_PASSWORDS = {
    "demo1234!",
    "password123!",
    "qwerty123456!",
    "vela123456!",
}


def _configure_database_url() -> None:
    if (
        os.environ.get("APP_ENV", "").strip().lower() == "production"
        and not os.environ.get("DATABASE_URL", "").strip()
    ):
        configure_database_url()


def _validate_password(password: str) -> None:
    encoded = password.encode("utf-8")
    if len(password) < 14:
        raise ValueError("密码至少需要 14 个字符")
    if len(encoded) > 72:
        raise ValueError("密码 UTF-8 编码后不能超过 72 字节")
    if password.lower() in COMMON_PASSWORDS:
        raise ValueError("密码属于已知演示或常见密码")
    categories = sum(
        bool(pattern.search(password))
        for pattern in (
            re.compile(r"[a-z]"),
            re.compile(r"[A-Z]"),
            re.compile(r"\d"),
            re.compile(r"[^A-Za-z0-9]"),
        )
    )
    if categories < 3 and len(password) < 20:
        raise ValueError("少于 20 字符的密码须包含大小写字母、数字、符号中的至少三类")


def _read_password() -> str:
    password = getpass.getpass("新用户密码（输入不会显示）：")
    _validate_password(password)
    confirmation = getpass.getpass("再次输入密码：")
    if password != confirmation:
        raise ValueError("两次输入的密码不一致")
    return password


def _resolve_organization(requested: str | None) -> str | None:
    """Bind production users to the instance's single allowed organisation."""

    requested_value = requested.strip() if requested else None
    if requested_value and len(requested_value) > 255:
        raise ValueError("组织名称不能超过 255 个字符")
    if os.environ.get("APP_ENV", "").strip().lower() != "production":
        return requested_value

    instance_organization = os.environ.get("INSTANCE_ORGANIZATION", "").strip()
    if not instance_organization:
        raise RuntimeError("INSTANCE_ORGANIZATION is required to provision a production user")
    if len(instance_organization) > 255:
        raise RuntimeError("INSTANCE_ORGANIZATION cannot exceed 255 characters")
    if requested_value and requested_value != instance_organization:
        raise ValueError("用户组织必须与 INSTANCE_ORGANIZATION 完全一致")
    return instance_organization


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="安全创建一个 Vela 本地用户")
    parser.add_argument("--email", required=True)
    parser.add_argument("--full-name", required=True)
    parser.add_argument("--organization", default=None)
    parser.add_argument("--role", choices=ALLOWED_ROLES, required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    password = _read_password()
    _configure_database_url()

    # Import after DATABASE_URL is finalized because the SQLAlchemy engine is
    # intentionally constructed from immutable process configuration.
    from email_validator import EmailNotValidError, validate_email
    from sqlalchemy import func

    from app.core.database import SessionLocal
    from app.core.security import get_password_hash
    from app.models.user import User
    from app.services.audit import write_audit_log

    try:
        normalized_email = validate_email(
            args.email,
            check_deliverability=False,
        ).normalized.lower()
    except EmailNotValidError as exc:
        raise ValueError("邮箱格式无效") from exc

    full_name = args.full_name.strip()
    if not full_name or len(full_name) > 128:
        raise ValueError("姓名须为 1 至 128 个字符")
    organization = _resolve_organization(args.organization)

    with SessionLocal() as db:
        existing = db.query(User).filter(func.lower(User.email) == normalized_email).first()
        if existing is not None:
            raise ValueError("该邮箱已存在；本命令不会覆盖账号或重置密码")

        user = User(
            email=normalized_email,
            full_name=full_name,
            organization=organization,
            hashed_password=get_password_hash(password),
            role=args.role,
            auth_provider="local",
            external_subject=None,
            is_active=True,
            disclaimer_accepted=False,
            disclaimer_accepted_at=None,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        write_audit_log(
            db,
            user=user,
            action="user.provisioned_by_operator",
            resource_type="user",
            resource_id=str(user.id),
            detail=f"role={args.role}; disclaimer_pending=true",
        )

    print(f"Created local user {normalized_email} with role {args.role}; disclaimer pending.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2) from None
