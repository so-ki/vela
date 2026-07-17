from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts/create_user.py"
SPEC = importlib.util.spec_from_file_location("create_user", MODULE_PATH)
assert SPEC and SPEC.loader
create_user = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(create_user)


@pytest.mark.parametrize(
    "password",
    [
        "short",
        "Demo1234!",
        "onlylowercase14",
        "A" * 73,
    ],
)
def test_password_policy_rejects_weak_or_unsupported_passwords(password: str):
    with pytest.raises(ValueError):
        create_user._validate_password(password)


@pytest.mark.parametrize(
    "password",
    [
        "Vela-Pilot-2026!",
        "这是一段足够长且很难猜测的专用中文安全口令",
    ],
)
def test_password_policy_accepts_strong_passwords(password: str):
    create_user._validate_password(password)


def test_production_database_password_is_url_encoded(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("POSTGRES_PASSWORD", "long-password@%:/ value")
    monkeypatch.delenv("DATABASE_URL", raising=False)

    create_user._configure_database_url()

    assert create_user.os.environ["DATABASE_URL"] == (
        "postgresql+psycopg2://vela:long-password%40%25%3A%2F%20value@db:5432/vela"
    )


def test_production_user_is_bound_to_instance_organization(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("INSTANCE_ORGANIZATION", "试点企业")

    assert create_user._resolve_organization(None) == "试点企业"
    assert create_user._resolve_organization("试点企业") == "试点企业"
    with pytest.raises(ValueError):
        create_user._resolve_organization("另一家企业")


def test_production_user_requires_instance_organization(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("INSTANCE_ORGANIZATION", raising=False)

    with pytest.raises(RuntimeError):
        create_user._resolve_organization(None)
