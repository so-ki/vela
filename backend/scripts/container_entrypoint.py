#!/usr/bin/env python3
"""Fail-closed production entrypoint for the backend container."""

from __future__ import annotations

import os
import subprocess
import sys
from urllib.parse import quote


DEFAULT_OR_WEAK_SECRETS = {
    "change-me",
    "changeme",
    "dev-secret-key-change-in-production",
    "replace-me",
    "vela-dev-secret-key-change-in-production",
}
DEFAULT_OR_WEAK_DATABASE_PASSWORDS = {
    "change-me",
    "changeme",
    "password",
    "postgres",
    "replace-me",
    "vela",
    "vela_change_me",
}


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"required production environment variable is missing: {name}")
    return value


def main() -> int:
    if os.environ.get("APP_ENV", "").strip().lower() != "production":
        raise RuntimeError("production image requires APP_ENV=production")

    secret_key = _required("SECRET_KEY")
    if len(secret_key) < 32 or secret_key.lower() in DEFAULT_OR_WEAK_SECRETS:
        raise RuntimeError("SECRET_KEY must be a non-default value of at least 32 characters")

    database_password = _required("POSTGRES_PASSWORD")
    if (
        len(database_password) < 16
        or database_password.lower() in DEFAULT_OR_WEAK_DATABASE_PASSWORDS
    ):
        raise RuntimeError(
            "POSTGRES_PASSWORD must be a non-default value of at least 16 characters"
        )
    encoded_password = quote(database_password, safe="")
    os.environ["DATABASE_URL"] = (
        f"postgresql+psycopg2://vela:{encoded_password}@db:5432/vela"
    )

    if os.environ.get("SEED_DEMO_USERS", "false").strip().lower() == "true":
        subprocess.run([sys.executable, "scripts/seed_demo_user.py"], check=True)

    command = [
        "gunicorn",
        "app.main:app",
        "-k",
        "uvicorn.workers.UvicornWorker",
        "-b",
        "0.0.0.0:8000",
        "--workers",
        "2",
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
