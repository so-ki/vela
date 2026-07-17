from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.services.auth_service as auth_service
import app.services.sso_service as sso_service
import app.api.auth as auth_api
from app.core.config import Settings, validate_runtime_configuration
from app.core.database import Base
from app.core.database import validate_instance_database_boundary
from app.models.user import User
from app.schemas.auth import UserRegister


def _settings(**overrides) -> Settings:
    values = {
        "app_env": "test",
        "debug": False,
        "secret_key": "test-only-secret-2026-adequate-diversity-48chars",
        "access_token_expire_minutes": 60,
        "algorithm": "HS256",
        "allow_open_registration": True,
        "allow_password_login": True,
        "rate_limit_enabled": True,
        "instance_organization": "试点企业",
        "sso_enabled": False,
        "corpus_agent_enabled": False,
        "llm_polish_enabled": False,
        "cors_origins": "https://pilot.example",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


@pytest.fixture()
def db(tmp_path: Path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'auth-hardening.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        yield session


def test_public_registration_forbids_role_input_and_creates_business(db, monkeypatch):
    with pytest.raises(ValidationError):
        UserRegister(
            email="attacker@example.com",
            password="StrongPass123!",
            full_name="Attacker",
            accept_disclaimer=True,
            role="legal",
        )

    monkeypatch.setattr(auth_service, "get_settings", lambda: _settings())
    payload = UserRegister(
        email="business@example.com",
        password="StrongPass123!",
        full_name="Business User",
        accept_disclaimer=True,
    )
    user = auth_service.register_user(db, payload)
    assert user.role == "business"


def test_sso_privileged_roles_require_exact_configured_group(monkeypatch):
    settings = _settings(
        sso_admin_groups="vela-admins",
        sso_legal_groups="vela-legal",
        sso_business_groups="vela-business",
        sso_default_role="legal",
    )
    monkeypatch.setattr(sso_service, "get_settings", lambda: settings)

    assert sso_service._resolve_role(None) == "business"
    assert sso_service._resolve_role(["admin-ish", "Vela-LegalOps"]) == "business"
    assert sso_service._resolve_role(["VELA-LEGAL"]) == "legal"
    assert sso_service._resolve_role(["vela-admins"]) == "admin"


def test_disabled_sso_login_does_not_allocate_state(monkeypatch):
    settings = _settings(sso_enabled=False)
    monkeypatch.setattr(auth_api, "get_settings", lambda: settings)
    auth_api._SSO_STATES.clear()

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(auth_api.sso_login())
    assert exc_info.value.status_code == 503
    assert auth_api._SSO_STATES == {}


def test_sso_cannot_take_over_local_account_or_rebind_subject(db, monkeypatch):
    settings = _settings(sso_jit_provision=True, sso_legal_groups="vela-legal")
    monkeypatch.setattr(sso_service, "get_settings", lambda: settings)
    db.add(
        User(
            email="owner@example.com",
            full_name="Owner",
            hashed_password="unused",
            role="legal",
            auth_provider="local",
            is_active=True,
            disclaimer_accepted=True,
        )
    )
    db.commit()

    with pytest.raises(HTTPException) as exc_info:
        sso_service._get_or_create_sso_user(
            db,
            email="owner@example.com",
            full_name="Impostor",
            issuer="https://idp.example",
            subject="attacker-subject",
            groups=["vela-legal"],
        )
    assert getattr(exc_info.value, "status_code", None) == 409

    created = sso_service._get_or_create_sso_user(
        db,
        email="new@example.com",
        full_name="New User",
        issuer="https://idp.example",
        subject="stable-subject",
        groups=[],
    )
    assert created.role == "business"
    assert created.external_subject and created.external_subject.startswith("oidc:")

    with pytest.raises(HTTPException) as rebind_exc:
        sso_service._get_or_create_sso_user(
            db,
            email="new@example.com",
            full_name="New User",
            issuer="https://idp.example",
            subject="different-subject",
            groups=[],
        )
    assert getattr(rebind_exc.value, "status_code", None) == 409


def test_production_configuration_enforces_controlled_pilot_boundary():
    safe = _settings(
        app_env="production",
        allow_open_registration=False,
        deployment_mode="single_tenant",
    )
    validate_runtime_configuration(safe)

    unsafe_variants = (
        {"allow_open_registration": True},
        {"rate_limit_enabled": False},
        {"sso_enabled": True},
        {"corpus_agent_enabled": True},
        {"llm_polish_enabled": True},
        {"deployment_mode": "multi_tenant"},
        {"instance_organization": ""},
        {"instance_organization": "replace-with-customer-organization"},
        {"instance_organization": "Example Corp"},
        {"instance_organization": "x" * 256},
        {"secret_key": "short"},
        {"secret_key": "x" * 48},
        {"secret_key": "replace-with-openssl-rand-hex-32"},
        {"secret_key": "change-me-in-production-use-openssl-rand-hex-32"},
        {"access_token_expire_minutes": 61},
        {"algorithm": "none"},
        {"cors_origins": "*"},
        {"frontend_url": "http://pilot.example"},
        {"public_api_url": "http://pilot.example/api/v1"},
        {"cors_origins": "http://pilot.example"},
    )
    for unsafe in unsafe_variants:
        values = {
            "app_env": "production",
            "allow_open_registration": False,
            "deployment_mode": "single_tenant",
            **unsafe,
        }
        with pytest.raises(RuntimeError):
            validate_runtime_configuration(_settings(**values))


def test_app_env_whitespace_cannot_bypass_production_gate():
    unsafe = _settings(
        app_env=" production ",
        debug=True,
        allow_open_registration=True,
        rate_limit_enabled=False,
    )

    assert unsafe.app_env == "production"
    assert unsafe.is_production is True
    with pytest.raises(RuntimeError):
        validate_runtime_configuration(unsafe)


@pytest.mark.parametrize("value", ["", "prod", "staging", "production-debug"])
def test_unknown_app_env_is_rejected(value: str):
    with pytest.raises(ValidationError, match="APP_ENV"):
        _settings(app_env=value)


def test_production_login_rejects_cross_organization_account(db, monkeypatch):
    settings = _settings(
        app_env="production",
        allow_open_registration=False,
        instance_organization="试点企业",
    )
    monkeypatch.setattr(auth_service, "get_settings", lambda: settings)
    db.add(
        User(
            email="legacy@example.com",
            full_name="Legacy User",
            organization="另一家企业",
            hashed_password=auth_service.get_password_hash("StrongPass123!"),
            role="legal",
            auth_provider="local",
            is_active=True,
            disclaimer_accepted=True,
        )
    )
    db.commit()

    with pytest.raises(HTTPException) as exc_info:
        auth_service.authenticate_user(db, "legacy@example.com", "StrongPass123!")
    assert exc_info.value.status_code == 403


def test_production_startup_rejects_restored_cross_organization_database(db):
    settings = _settings(
        app_env="production",
        allow_open_registration=False,
        instance_organization="试点企业",
    )
    validate_instance_database_boundary(runtime_settings=settings, db=db)
    db.add(
        User(
            email="old@example.com",
            full_name="Old Tenant",
            organization="旧客户",
            hashed_password="unused",
            role="business",
            auth_provider="local",
            is_active=False,
            disclaimer_accepted=True,
        )
    )
    db.commit()

    with pytest.raises(RuntimeError, match="INSTANCE_ORGANIZATION"):
        validate_instance_database_boundary(runtime_settings=settings, db=db)
