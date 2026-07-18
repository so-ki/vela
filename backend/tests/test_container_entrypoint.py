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
BACKEND_ROOT = MODULE_PATH.parents[1]


def _production_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SECRET_KEY", "test-entrypoint-secret-2026-with-diversity")
    monkeypatch.setenv("POSTGRES_PASSWORD", "test-db-password-2026!")
    # A legacy variable must not be able to create fixed-password users.
    monkeypatch.setenv("SEED_DEMO_USERS", "true")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("VELA_ENTRYPOINT_MODE", raising=False)


def test_production_entrypoint_is_importable_as_the_packaged_module() -> None:
    env = os.environ.copy()
    env.update(
        {
            "APP_ENV": "production",
            "SECRET_KEY": "module-import-secret-2026-with-diversity",
            "POSTGRES_PASSWORD": "module-import-db-password-2026!",
            "VELA_ENTRYPOINT_MODE": "invalid-mode-probe",
        }
    )

    result = subprocess.run(
        [os.sys.executable, "-m", "scripts.container_entrypoint"],
        cwd=BACKEND_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    assert "VELA_ENTRYPOINT_MODE must be check, migrate, or web" in result.stderr
    assert "ModuleNotFoundError" not in result.stderr


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
        " leading-whitespace-password-2026!",
        "trailing-whitespace-password-2026! ",
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


def test_exec_process_can_configure_the_same_production_database_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _production_env(monkeypatch)
    monkeypatch.setenv("POSTGRES_PASSWORD", "exec-password@%:/ value")

    configured = container_entrypoint.configure_database_url()

    assert configured == (
        "postgresql+psycopg2://vela:exec-password%40%25%3A%2F%20value@db:5432/vela"
    )
    assert os.environ["DATABASE_URL"] == configured


def test_exec_process_configures_url_before_database_module_import() -> None:
    env = os.environ.copy()
    env.update(
        {
            "APP_ENV": "production",
            "POSTGRES_PASSWORD": "exec-password@%:/ value",
        }
    )
    env.pop("DATABASE_URL", None)
    result = subprocess.run(
        [
            os.sys.executable,
            "-c",
            (
                "from scripts.container_entrypoint import configure_database_url; "
                "configure_database_url(); "
                "from app.core.database import settings; "
                "print(settings.database_url)"
            ),
        ],
        cwd=BACKEND_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == (
        "postgresql+psycopg2://vela:exec-password%40%25%3A%2F%20value@db:5432/vela"
    )


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


def test_check_mode_asserts_head_and_schema_drift_without_mutating_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _production_env(monkeypatch)
    monkeypatch.setenv("VELA_ENTRYPOINT_MODE", "check")
    checks: list[str] = []
    subprocess_calls: list[list[str]] = []
    monkeypatch.setattr(
        container_entrypoint,
        "_assert_database_at_heads",
        lambda: checks.append("heads"),
    )
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda command, *, cwd=None, check: subprocess_calls.append(command),
    )
    monkeypatch.setattr(
        os,
        "execvp",
        lambda _program, _command: pytest.fail("web must not start in check mode"),
    )

    assert container_entrypoint.main() == 0
    assert checks == ["heads"]
    assert len(subprocess_calls) == 1
    assert subprocess_calls[0][-1] == "check"
    assert "upgrade" not in subprocess_calls[0]


def test_check_mode_rejects_database_behind_head(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _production_env(monkeypatch)
    monkeypatch.setenv("VELA_ENTRYPOINT_MODE", "check")
    monkeypatch.setattr(
        container_entrypoint,
        "_assert_database_at_heads",
        lambda: (_ for _ in ()).throw(RuntimeError("database migration heads do not match")),
    )
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *_args, **_kwargs: pytest.fail("drift check must not run when head check fails"),
    )

    with pytest.raises(RuntimeError, match="migration heads"):
        container_entrypoint.main()


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
