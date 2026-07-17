"""Seed demo business and legal users for local development."""

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import func
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.database import SessionLocal, init_db
from app.core.roles import ROLE_BUSINESS, ROLE_LEGAL
from app.core.security import get_password_hash, verify_password
from app.models.user import User
from app.services.cold_start_service import (
    PLAYBOOK_PROFILE_SCHEMA_VERSION,
    default_compliance_dimensions_for_profile,
    save_playbook_profile,
    suggested_checklist_codes_for_profile,
)

DEMO_LEGAL_PROFILE_VERSION = "demo-legal-playbook-v1.0.0"

DEMO_USERS = [
    {
        "email": "legal@demo.vela",
        "full_name": "演示法务",
        "organization": "Demo Corp · 法务部",
        "password": "Demo1234!",
        "role": ROLE_LEGAL,
    },
    {
        "email": "biz@demo.vela",
        "full_name": "演示业务",
        "organization": "Demo Corp · 投资部",
        "password": "Demo1234!",
        "role": ROLE_BUSINESS,
    },
]


def _demo_organization(spec: dict[str, object]) -> str:
    if os.environ.get("APP_ENV", "").strip().lower() == "production":
        organization = os.environ.get("INSTANCE_ORGANIZATION", "").strip()
        if not organization:
            raise RuntimeError("INSTANCE_ORGANIZATION is required for production smoke seeding")
        return organization
    return str(spec["organization"])


def _password_matches(user: User, password: str) -> bool:
    if not user.hashed_password:
        return False
    try:
        return verify_password(password, user.hashed_password)
    except (TypeError, ValueError):
        return False


def _set_if_changed(user: User, field: str, value: object) -> bool:
    if getattr(user, field) == value:
        return False
    setattr(user, field, value)
    return True


def _demo_legal_profile(user: User) -> dict[str, object]:
    industry_focus = ["new_energy"]
    return {
        "completed": True,
        "profile_schema_version": PLAYBOOK_PROFILE_SCHEMA_VERSION,
        "profile_version": DEMO_LEGAL_PROFILE_VERSION,
        "profile_source": "demo_seed",
        "completed_at": user.created_at.isoformat() if user.created_at else None,
        "org_name": "Demo Corp · 法务部",
        "primary_jurisdiction": "brazil",
        "industry_focus": industry_focus,
        "default_compliance_dimensions": default_compliance_dimensions_for_profile(industry_focus),
        "suggested_checklist_codes": suggested_checklist_codes_for_profile(industry_focus),
        "output_language": "zh_pt_bilingual",
        "risk_tolerance": "balanced",
        "match_threshold_adjustment": 0,
        "contract_house_rules": "",
        "brief_template_style": "law_firm_memo",
        "external_counsel_triggers": "S3 硬阻断项或高优先级核查项缺少有效法源时，须由当地律师复核。",
        "playbook_md": (
            "# Demo Corp · 法务部 · Vela Playbook Profile\n\n"
            "- 法域：巴西\n- 行业：新能源制造 / 绿地设厂\n"
            "- 输出：中文 + 葡语双语\n- 门控：均衡型\n- 底稿风格：律所备忘录体例\n"
        ),
    }


def seed_demo_users(db: Session) -> dict[str, User]:
    """Converge the two documented public demo accounts to a usable local state."""
    now = datetime.now(timezone.utc)
    users: dict[str, User] = {}
    outcomes: dict[str, str] = {}

    for spec in DEMO_USERS:
        email = str(spec["email"]).lower()
        organization = _demo_organization(spec)
        user = db.query(User).filter(func.lower(User.email) == email).first()
        if user is None:
            user = User(
                email=email,
                full_name=str(spec["full_name"]),
                organization=organization,
                hashed_password=get_password_hash(str(spec["password"])),
                role=str(spec["role"]),
                auth_provider="local",
                external_subject=None,
                is_active=True,
                disclaimer_accepted=True,
                disclaimer_accepted_at=now,
            )
            db.add(user)
            outcomes[email] = "Created"
        else:
            changed = False
            changed |= _set_if_changed(user, "email", email)
            changed |= _set_if_changed(user, "full_name", str(spec["full_name"]))
            changed |= _set_if_changed(user, "organization", organization)
            changed |= _set_if_changed(user, "role", str(spec["role"]))
            changed |= _set_if_changed(user, "auth_provider", "local")
            changed |= _set_if_changed(user, "external_subject", None)
            changed |= _set_if_changed(user, "is_active", True)
            changed |= _set_if_changed(user, "disclaimer_accepted", True)
            if user.disclaimer_accepted_at is None:
                user.disclaimer_accepted_at = now
                changed = True
            if not _password_matches(user, str(spec["password"])):
                user.hashed_password = get_password_hash(str(spec["password"]))
                changed = True
            outcomes[email] = "Updated" if changed else "Verified"
        users[email] = user

    db.commit()
    for user in users.values():
        db.refresh(user)

    legal_user = users["legal@demo.vela"]
    save_playbook_profile(
        legal_user.id,
        _demo_legal_profile(legal_user),
        owner_email=legal_user.email,
        owner_auth_provider=legal_user.auth_provider,
        owner_external_subject=legal_user.external_subject,
    )

    for spec in DEMO_USERS:
        email = str(spec["email"]).lower()
        print(f"{outcomes[email]} demo user: {email} ({spec['role']})")
    return users


def seed() -> None:
    init_db()
    db = SessionLocal()
    try:
        seed_demo_users(db)
    finally:
        db.close()


if __name__ == "__main__":
    seed()
