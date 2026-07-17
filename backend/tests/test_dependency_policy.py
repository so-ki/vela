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
    for relative_path in (
        "docker/Dockerfile.backend",
        "docker/Dockerfile.backend.prod",
    ):
        content = (REPOSITORY_ROOT / relative_path).read_text(encoding="utf-8")
        assert content.startswith("FROM python:3.12-slim\n")
        assert "pip install --no-cache-dir -r requirements.lock" in content
        assert "requirements-rag.txt" not in content
