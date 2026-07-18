from __future__ import annotations

import hashlib

import pytest
from pydantic import ValidationError

from app.schemas.delivery_assurance import (
    CredentialCreateRequest,
    LegalContentManifestRequest,
)


def _sha(label: str) -> str:
    return hashlib.sha256(label.encode()).hexdigest()


def test_external_evidence_hash_rejects_obvious_placeholder() -> None:
    with pytest.raises(ValidationError, match="占位值"):
        CredentialCreateRequest(
            holder_name="Brazil Expert",
            jurisdiction="BR",
            authority="OAB/SP",
            registration_number="123456",
            official_register_url="https://consulta.oab.org.br/",
            submitted_evidence_hash="0" * 64,
        )


def test_content_manifest_rejects_placeholder_but_accepts_realistic_digests() -> None:
    values = {
        "capability_pack_id": "brazil_new_energy_greenfield",
        "capability_pack_version": "1.0",
        "capability_pack_hash": _sha("pack"),
        "rules_artifact_hash": _sha("rules"),
        "corpus_artifact_hash": _sha("corpus"),
        "gold_dataset_sha256": _sha("gold"),
        "evaluation_policy_sha256": _sha("policy"),
        "evaluation_run_sha256": _sha("run"),
        "regression_status": "passed",
        "primary_credential_id": "10000000-0000-0000-0000-000000000001",
        "secondary_credential_id": "10000000-0000-0000-0000-000000000002",
        "limitations": "Certification is limited to this exact frozen release.",
    }
    assert LegalContentManifestRequest(**values).capability_pack_hash == _sha("pack")
    values["gold_dataset_sha256"] = "a" * 64
    with pytest.raises(ValidationError, match="占位值"):
        LegalContentManifestRequest(**values)
