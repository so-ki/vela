from __future__ import annotations

import importlib.util
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
