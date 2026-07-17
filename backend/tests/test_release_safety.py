from __future__ import annotations

import hashlib
import importlib.util
import stat
from pathlib import Path

import pytest


MODULE_PATH = Path(__file__).resolve().parents[2] / "scripts/release_safety.py"
SPEC = importlib.util.spec_from_file_location("release_safety", MODULE_PATH)
assert SPEC and SPEC.loader
release_safety = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release_safety)


@pytest.mark.parametrize(
    "content",
    [
        b"secret_key: synthetic-sensitive-value-123456789",
        b"postgres_password: synthetic-sensitive-value-123456789",
        b'{"secret_key":"synthetic-sensitive-value-123456789"}',
    ],
)
def test_secret_detector_rejects_yaml_and_minified_json(content: bytes) -> None:
    assert "sensitive-assignment" in release_safety._secret_detectors(content)


@pytest.mark.parametrize(
    "content",
    [
        b'secret_key: str = "dev-secret-key-change-in-production"',
        b"SSO_CLIENT_SECRET=<managed-secret>",
    ],
)
def test_secret_detector_allows_type_annotations_and_placeholders(content: bytes) -> None:
    assert release_safety._secret_detectors(content) == []


def test_release_checksum_sidecar_matches_archive_and_is_shareable(tmp_path) -> None:
    archive = tmp_path / "vela-rc.zip"
    archive.write_bytes(b"deterministic release bytes")

    digest, sidecar = release_safety._write_sha256_sidecar(archive)

    assert digest == hashlib.sha256(archive.read_bytes()).hexdigest()
    assert sidecar.read_text(encoding="utf-8") == f"{digest}  {archive.name}\n"
    assert stat.S_IMODE(sidecar.stat().st_mode) == 0o644
    assert list(tmp_path.glob("*.tmp.sha256")) == []


def test_internal_markdown_link_validator_rejects_omitted_release_file() -> None:
    with pytest.raises(release_safety.BoundaryError, match="Markdown link"):
        release_safety._validate_internal_markdown_links(
            {"README.md": b"[missing](docs/not-packaged.docx)"}
        )


def test_internal_markdown_link_validator_allows_packaged_and_external_targets() -> None:
    release_safety._validate_internal_markdown_links(
        {
            "README.md": b"[guide](docs/guide.md) [web](https://example.com)",
            "docs/guide.md": b"[manifest](../backend/manifest.json)",
            "backend/manifest.json": b"{}",
        }
    )


def test_release_allowlist_keeps_reproducible_experiment_evidence() -> None:
    files = release_safety._collect_package_files()
    expected = {
        ".github/workflows/ci.yml",
        "backend/evals/legal_quality_gate_v1.jsonl",
        "backend/evals/state_metadata_coverage_v1.json",
        "backend/evals/ingestion_qa_v3.json",
        "backend/evals/rule_cards/brazil_sp_environment_dual_track_v0.1.json",
        "backend/scripts/run_state_metadata_coverage.py",
        "backend/scripts/run_ingestion_qa.py",
        "backend/scripts/render_official_pages_to_pdf.mjs",
    }
    assert expected <= files.keys()


def test_packaged_release_contains_every_static_check_docker_dependency() -> None:
    """The ZIP must be independently auditable, not only buildable in the repo."""

    files = release_safety._collect_package_files()
    expected = {
        ".github/workflows/ci.yml",
        ".dockerignore",
        "backend/.dockerignore",
        "frontend/.dockerignore",
        "frontend/e2e/production-smoke.spec.ts",
        "frontend/playwright.config.ts",
        "docker-compose.yml",
        "docker-compose.prod.yml",
        "docker/Dockerfile.backend",
        "docker/Dockerfile.backend.prod",
        "docker/Dockerfile.frontend",
        "docker/Dockerfile.frontend.prod",
        "docker/Dockerfile.postgres.prod",
        "docker/nginx.conf",
        "backend/scripts/__init__.py",
        "backend/scripts/container_entrypoint.py",
        "frontend/vite.config.ts",
        "scripts/prod_smoke.sh",
    }
    assert expected <= files.keys()


def test_production_smoke_preserves_failure_evidence_before_cleanup() -> None:
    content = (release_safety.ROOT / "scripts/prod_smoke.sh").read_text(encoding="utf-8")

    assert "local status=$?" in content
    assert "ps --all >&2 || true" in content
    assert "logs --no-color --tail=200 >&2 || true" in content
    assert content.index("logs --no-color --tail=200") < content.index(
        "down -v --remove-orphans"
    )


def test_production_smoke_streams_seed_into_read_only_backend() -> None:
    content = (release_safety.ROOT / "scripts/prod_smoke.sh").read_text(encoding="utf-8")

    assert '"${COMPOSE[@]}" cp ' not in content
    assert 'exec -T backend env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/app python -' in content
    assert '< "$ROOT/backend/scripts/seed_demo_user.py"' in content
