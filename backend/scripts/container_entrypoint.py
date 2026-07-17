#!/usr/bin/env python3
"""Fail-closed production entrypoint for the backend container."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
from urllib.parse import quote

from app.core.secret_policy import is_weak_secret

DEFAULT_OR_WEAK_DATABASE_PASSWORDS = {"password", "postgres", "vela", "vela_change_me"}
APP_ROOT = Path(__file__).resolve().parents[1]
ALEMBIC_CONFIG = APP_ROOT / "alembic.ini"


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"required production environment variable is missing: {name}")
    return value


def configure_database_url() -> str:
    """Set the production PostgreSQL URL in the current process.

    Docker exec processes do not inherit environment mutations made by PID 1,
    so administrative and smoke commands must call this before importing the
    application database module.
    """

    if os.environ.get("APP_ENV", "").strip().lower() != "production":
        raise RuntimeError("production database configuration requires APP_ENV=production")

    database_password = _required("POSTGRES_PASSWORD")
    if database_password != os.environ["POSTGRES_PASSWORD"]:
        raise RuntimeError("POSTGRES_PASSWORD must not start or end with whitespace")
    if is_weak_secret(database_password, min_length=16, min_unique=6) or (
        database_password.lower() in DEFAULT_OR_WEAK_DATABASE_PASSWORDS
    ):
        raise RuntimeError(
            "POSTGRES_PASSWORD must be a diverse, non-default value of at least 16 characters"
        )
    encoded_password = quote(database_password, safe="")
    os.environ["DATABASE_URL"] = (
        f"postgresql+psycopg2://vela:{encoded_password}@db:5432/vela"
    )
    return os.environ["DATABASE_URL"]


def _run_migrations() -> None:
    subprocess.run(
        [
            sys.executable,
            "-m",
            "alembic",
            "-c",
            str(ALEMBIC_CONFIG),
            "upgrade",
            "head",
        ],
        cwd=APP_ROOT,
        check=True,
    )


def _assert_database_at_heads() -> None:
    """Fail unless the connected database is exactly at every migration head."""

    from alembic.config import Config
    from alembic.runtime.migration import MigrationContext
    from alembic.script import ScriptDirectory
    from sqlalchemy import create_engine

    config = Config(str(ALEMBIC_CONFIG))
    expected_heads = set(ScriptDirectory.from_config(config).get_heads())
    engine = create_engine(_required("DATABASE_URL"))
    try:
        with engine.connect() as connection:
            current_heads = set(MigrationContext.configure(connection).get_current_heads())
    finally:
        engine.dispose()
    if current_heads != expected_heads:
        raise RuntimeError(
            "database migration heads do not match the packaged Alembic heads: "
            f"current={sorted(current_heads)} expected={sorted(expected_heads)}"
        )


def _run_schema_drift_check() -> None:
    subprocess.run(
        [
            sys.executable,
            "-m",
            "alembic",
            "-c",
            str(ALEMBIC_CONFIG),
            "check",
        ],
        cwd=APP_ROOT,
        check=True,
    )


def main() -> int:
    if os.environ.get("APP_ENV", "").strip().lower() != "production":
        raise RuntimeError("production image requires APP_ENV=production")

    secret_key = _required("SECRET_KEY")
    if is_weak_secret(secret_key, min_length=32, min_unique=8):
        raise RuntimeError(
            "SECRET_KEY must be a diverse, non-default value of at least 32 characters"
        )

    configure_database_url()

    mode = os.environ.get("VELA_ENTRYPOINT_MODE", "web").strip().lower()
    if mode not in {"check", "migrate", "web"}:
        raise RuntimeError("VELA_ENTRYPOINT_MODE must be check, migrate, or web")

    if mode == "check":
        _assert_database_at_heads()
        _run_schema_drift_check()
        return 0

    # Alembic is the only production DDL path.  A standalone web container
    # performs the same idempotent upgrade as the compose migration gate.
    _run_migrations()
    if mode == "migrate":
        return 0

    command = [
        "gunicorn",
        "app.main:app",
        "-k",
        "uvicorn.workers.UvicornWorker",
        "-b",
        "0.0.0.0:8000",
        "--workers",
        "1",
        "--timeout",
        "180",
    ]
    os.execvp(command[0], command)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        print(f"FATAL: {exc}", file=sys.stderr)
        raise SystemExit(2) from None
