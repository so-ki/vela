from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import subprocess

import pytest

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts/container_entrypoint.py"
SPEC = importlib.util.spec_from_file_location("container_entrypoint", MODULE_PATH)
assert SPEC and SPEC.loader
container_entrypoint = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(container_entrypoint)


def _production_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SECRET_KEY", "test-entrypoint-secret-2026-with-diversity")
    monkeypatch.setenv("POSTGRES_PASSWORD", "test-db-password-2026!")
    # A legacy variable must not be able to create fixed-password users.
    monkeypatch.setenv("SEED_DEMO_USERS", "true")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("VELA_ENTRYPOINT_MODE", raising=False)


@pytest.mark.parametrize(
    "secret",
    [
        "",
        "too-short",
        "dev-secret-key-change-in-production",
        "replace-with-openssl-rand-hex-32",
        "change-me-in-production-use-openssl-rand-hex-32",
        "x" * 48,
    ],
)
def test_production_entrypoint_rejects_missing_or_weak_secret(
    monkeypatch: pytest.MonkeyPatch,
    secret: str,
) -> None:
    _production_env(monkeypatch)
    monkeypatch.setenv("SECRET_KEY", secret)

    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        container_entrypoint.main()


@pytest.mark.parametrize(
    "password",
    [
        "",
        "too-short",
        "postgres",
        "vela_change_me",
        "replace-with-strong-password",
        "p" * 20,
    ],
)
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
    subprocess_calls: list[tuple[list[str], Path | str | None]] = []
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda command, *, cwd=None, check: subprocess_calls.append((command, cwd)),
    )
    monkeypatch.setattr(os, "execvp", lambda _program, command: executed.append(command))

    assert container_entrypoint.main() == 0
    assert os.environ["DATABASE_URL"] == (
        "postgresql+psycopg2://vela:long-password%40%25%3A%2F%20value@db:5432/vela"
    )
    assert subprocess_calls == [
        (
            [
                os.sys.executable,
                "-m",
                "alembic",
                "-c",
                str(container_entrypoint.ALEMBIC_CONFIG),
                "upgrade",
                "head",
            ],
            container_entrypoint.APP_ROOT,
        )
    ]
    assert executed and executed[0][0] == "gunicorn"


def test_migration_mode_exits_before_starting_web(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _production_env(monkeypatch)
    monkeypatch.setenv("VELA_ENTRYPOINT_MODE", "migrate")
    migrations: list[list[str]] = []
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda command, *, cwd=None, check: migrations.append(command),
    )
    monkeypatch.setattr(
        os,
        "execvp",
        lambda _program, _command: pytest.fail("web must not start in migration mode"),
    )

    assert container_entrypoint.main() == 0
    assert migrations and migrations[0][-2:] == ["upgrade", "head"]


def test_migration_failure_prevents_web_start(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _production_env(monkeypatch)

    def fail_migration(command, *, cwd=None, check):
        assert cwd == container_entrypoint.APP_ROOT
        assert check is True
        raise subprocess.CalledProcessError(1, command)

    monkeypatch.setattr(
        subprocess,
        "run",
        fail_migration,
    )
    monkeypatch.setattr(
        os,
        "execvp",
        lambda _program, _command: pytest.fail("web must not start after migration failure"),
    )

    with pytest.raises(subprocess.CalledProcessError):
        container_entrypoint.main()
