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


def main() -> int:
    if os.environ.get("APP_ENV", "").strip().lower() != "production":
        raise RuntimeError("production image requires APP_ENV=production")

    secret_key = _required("SECRET_KEY")
    if is_weak_secret(secret_key, min_length=32, min_unique=8):
        raise RuntimeError(
            "SECRET_KEY must be a diverse, non-default value of at least 32 characters"
        )

    database_password = _required("POSTGRES_PASSWORD")
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

    mode = os.environ.get("VELA_ENTRYPOINT_MODE", "web").strip().lower()
    if mode not in {"migrate", "web"}:
        raise RuntimeError("VELA_ENTRYPOINT_MODE must be either migrate or web")

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
