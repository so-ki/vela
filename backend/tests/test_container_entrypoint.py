from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import pytest

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts/container_entrypoint.py"
SPEC = importlib.util.spec_from_file_location("container_entrypoint", MODULE_PATH)
assert SPEC and SPEC.loader
container_entrypoint = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(container_entrypoint)


def _production_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SECRET_KEY", "s" * 32)
    monkeypatch.setenv("POSTGRES_PASSWORD", "p" * 20)
    monkeypatch.setenv("SEED_DEMO_USERS", "false")
    monkeypatch.delenv("DATABASE_URL", raising=False)


@pytest.mark.parametrize(
    "secret",
    ["", "too-short", "dev-secret-key-change-in-production"],
)
def test_production_entrypoint_rejects_missing_or_weak_secret(
    monkeypatch: pytest.MonkeyPatch,
    secret: str,
) -> None:
    _production_env(monkeypatch)
    monkeypatch.setenv("SECRET_KEY", secret)

    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        container_entrypoint.main()


@pytest.mark.parametrize("password", ["", "too-short", "postgres", "vela_change_me"])
def test_production_entrypoint_rejects_missing_or_weak_database_password(
    monkeypatch: pytest.MonkeyPatch,
    password: str,
) -> None:
    _production_env(monkeypatch)
    monkeypatch.setenv("POSTGRES_PASSWORD", password)

    with pytest.raises(RuntimeError, match="POSTGRES_PASSWORD"):
        container_entrypoint.main()


def test_production_entrypoint_url_encodes_database_password(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _production_env(monkeypatch)
    monkeypatch.setenv("POSTGRES_PASSWORD", "long-password@%:/ value")
    executed: list[list[str]] = []
    monkeypatch.setattr(os, "execvp", lambda _program, command: executed.append(command))

    assert container_entrypoint.main() == 0
    assert os.environ["DATABASE_URL"] == (
        "postgresql+psycopg2://vela:long-password%40%25%3A%2F%20value@db:5432/vela"
    )
    assert executed and executed[0][0] == "gunicorn"
