from __future__ import annotations

from pathlib import Path

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _active_requirement_lines(relative_path: str) -> list[str]:
    content = (REPOSITORY_ROOT / relative_path).read_text(encoding="utf-8")
    return [
        line.strip()
        for line in content.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def test_release_requirements_exclude_unfixed_chroma_runtime() -> None:
    for relative_path in (
        "backend/requirements.txt",
        "backend/requirements.lock",
        "backend/requirements-rag.txt",
    ):
        active_lines = [line.lower() for line in _active_requirement_lines(relative_path)]
        assert all(not line.startswith("chromadb") for line in active_lines)


def test_runtime_lock_contains_every_direct_pin() -> None:
    direct = [Requirement(line) for line in _active_requirement_lines("backend/requirements.txt")]
    locked = {
        canonicalize_name(requirement.name): requirement
        for requirement in (
            Requirement(line) for line in _active_requirement_lines("backend/requirements.lock")
        )
    }

    for requirement in direct:
        locked_requirement = locked[canonicalize_name(requirement.name)]
        assert locked_requirement.specifier == requirement.specifier

    assert _active_requirement_lines("backend/requirements-rag.txt") == ["-r requirements.lock"]


def test_backend_images_use_the_python_312_audited_matrix() -> None:
    development = (REPOSITORY_ROOT / "docker/Dockerfile.backend").read_text(
        encoding="utf-8"
    )
    production = (REPOSITORY_ROOT / "docker/Dockerfile.backend.prod").read_text(
        encoding="utf-8"
    )

    assert development.startswith("FROM python:3.12-slim\n")
    assert "pip install --no-cache-dir -r requirements.lock" in development

    assert production.startswith(
        "FROM python:3.12.13-alpine3.24@sha256:"
        "6d43704baacd1bfbe7c295d7f13079d5d8104ed33568873133f8fc69980419df\n"
    )
    assert "pip install --no-cache-dir --only-binary=:all: -r requirements.lock" in production
    assert "apt-get" not in production
    assert "curl" not in production
    assert "groupadd" not in production
    assert "useradd" not in production
    assert "addgroup -S vela" in production
    assert "adduser -S -D -H -h /app -G vela vela" in production

    assert "requirements-rag.txt" not in development
    assert "requirements-rag.txt" not in production
    assert 'CMD ["python", "-m", "scripts.container_entrypoint"]' in production
    assert "python scripts/container_entrypoint.py" not in production


def test_production_postgres_replaces_the_scanner_flagged_gosu_binary() -> None:
    content = (REPOSITORY_ROOT / "docker/Dockerfile.postgres.prod").read_text(
        encoding="utf-8"
    )

    assert content.startswith(
        "FROM postgres:16.14-alpine3.24@sha256:"
        "57c72fd2a128e416c7fcc499958864df5301e940bca0a56f58fddf30ffc07777\n"
    )
    assert "apk add --no-cache su-exec=0.3-r0" in content
    assert "test -x /sbin/su-exec" in content
    assert "rm -f /usr/local/bin/gosu /usr/local/bin/su-exec" in content
    assert "ln -s /sbin/su-exec" not in content
    assert 'test "$(grep -Fc \'exec gosu postgres' in content
    assert "sed -i 's|exec gosu postgres" in content
    assert 'test "$(grep -Fc \'exec /sbin/su-exec postgres' in content
    assert "! grep -Fq 'exec gosu postgres" in content
    assert 'bash -n "$entrypoint"' in content
    assert "test ! -e /usr/local/bin/gosu && test ! -L /usr/local/bin/gosu" in content
    assert "test ! -e /usr/local/bin/su-exec && test ! -L /usr/local/bin/su-exec" in content
    assert 'test "$(/sbin/su-exec postgres id -u)" = \'70\'' in content
    assert 'test "$(/sbin/su-exec postgres id -g)" = \'70\'' in content
    assert "'/var/lib/postgresql'" in content


def test_production_frontend_pins_bases_and_defines_pid_once() -> None:
    content = (REPOSITORY_ROOT / "docker/Dockerfile.frontend.prod").read_text(
        encoding="utf-8"
    )

    assert content.startswith(
        "FROM node:24-alpine@sha256:"
        "a0b9bf06e4e6193cf7a0f58816cc935ff8c2a908f81e6f1a95432d679c54fbfd AS build\n"
    )
    assert (
        "FROM nginx:1.30.4-alpine@sha256:"
        "59d10bca5c674965ef4ff884715000dd60ef5567c36663523f108eec8e4105d4\n"
    ) in content
    assert "sed -i 's|pid /var/run/nginx.pid;|pid /tmp/nginx.pid;|'" in content
    assert "nginx -t" in content
    assert 'CMD ["nginx", "-g", "daemon off;"]' in content
    assert "daemon off; pid " not in content
