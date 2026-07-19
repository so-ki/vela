"""Provision an isolated admin only inside the controlled finalist smoke stack."""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.container_entrypoint import configure_database_url


def seed() -> None:
    if os.environ.get("APP_ENV", "").strip().lower() != "production":
        raise RuntimeError("finalist smoke admin requires APP_ENV=production")
    if os.environ.get("INSTANCE_ORGANIZATION", "").strip() != "Vela controlled smoke":
        raise RuntimeError("finalist smoke admin is restricted to the disposable smoke instance")
    configure_database_url()

    from sqlalchemy import func

    from app.core.database import SessionLocal
    from app.core.security import get_password_hash
    from app.models.user import User
    from app.services.cold_start_service import (
        PLAYBOOK_PROFILE_SCHEMA_VERSION,
        default_compliance_dimensions_for_profile,
        save_playbook_profile,
        suggested_checklist_codes_for_profile,
    )

    now = datetime.now(timezone.utc)
    email = "admin@demo.vela"
    with SessionLocal() as db:
        if db.get_bind().dialect.name != "postgresql":
            raise RuntimeError("finalist smoke admin requires PostgreSQL")
        user = db.query(User).filter(func.lower(User.email) == email).first()
        if user is not None:
            raise RuntimeError("finalist smoke admin already exists; refusing overwrite")
        user = User(
            email=email,
            full_name="Finalist Admin",
            organization="Vela controlled smoke",
            hashed_password=get_password_hash("Demo1234!"),
            role="admin",
            auth_provider="local",
            is_active=True,
            disclaimer_accepted=True,
            disclaimer_accepted_at=now,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    industry_focus = ["new_energy"]
    save_playbook_profile(
        user.id,
        {
            "completed": True,
            "profile_schema_version": PLAYBOOK_PROFILE_SCHEMA_VERSION,
            "profile_version": "finalist-smoke-admin-v1",
            "profile_source": "finalist_smoke_seed",
            "completed_at": now.isoformat(),
            "org_name": "Vela controlled smoke",
            "primary_jurisdiction": "brazil",
            "industry_focus": industry_focus,
            "default_compliance_dimensions": default_compliance_dimensions_for_profile(
                industry_focus
            ),
            "suggested_checklist_codes": suggested_checklist_codes_for_profile(
                industry_focus
            ),
            "output_language": "zh_pt_bilingual",
            "risk_tolerance": "balanced",
            "match_threshold_adjustment": 0,
            "contract_house_rules": "",
            "brief_template_style": "law_firm_memo",
            "external_counsel_triggers": "Smoke-only profile; no external evidence.",
            "playbook_md": "# Finalist smoke admin\n\nEngineering verification only.",
        },
        owner_email=user.email,
        owner_auth_provider=user.auth_provider,
        owner_external_subject=user.external_subject,
    )
    print("Created smoke-only admin: admin@demo.vela")


if __name__ == "__main__":
    seed()
