from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from fastapi import HTTPException
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api import system
from app.core.database import Base
from app.models.delivery_assurance import ScenarioDeliveryRelease, ScenarioExpertAttestation
from app.models.mechanism import ClaimCompilation, CoverageProof
from app.services.version_readiness_service import build_version_readiness_report


@pytest.fixture()
def readiness_db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'readiness.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as db:
        yield db


def _add_versioned_rows(db, *, version: str) -> None:
    now = datetime.now(timezone.utc)
    compilation = ClaimCompilation(
        id="compilation-1",
        scenario_id=1,
        compiler_version=version,
        input_hash="1" * 64,
        output_hash="2" * 64,
        input_snapshot={},
        denominator_count=0,
        ready_count=0,
        refused_count=0,
        created_by=1,
    )
    proof = CoverageProof(
        id="proof-1",
        scenario_id=1,
        compilation_id=compilation.id,
        denominator_ref="readiness:test",
        denominator_hash="3" * 64,
        denominator_count=0,
        covered_count=0,
        uncovered_count=0,
        unanswerable_count=0,
        proof={"schema_version": version},
        proof_hash="4" * 64,
        created_by=1,
    )
    attestation = ScenarioExpertAttestation(
        id="attestation-1",
        scenario_id=1,
        credential_id="credential-1",
        signed_by=1,
        snapshot={"schema_version": version},
        snapshot_hash="5" * 64,
        artifact_manifest=[],
        artifact_manifest_hash="6" * 64,
        signature_format="test",
        signature_artifact_hash="7" * 64,
        signature_validation_url="https://example.invalid/signature",
        signature_validation_report_hash="8" * 64,
        signature_validation_status="submitted",
        certificate_subject="synthetic readiness fixture",
        certificate_serial="fixture",
        certificate_valid_until=now + timedelta(days=1),
        statement="synthetic readiness fixture only",
        limitations="not evidence",
        status="pending_validation",
        signed_at=now,
        expires_at=now + timedelta(days=1),
    )
    release = ScenarioDeliveryRelease(
        id="release-1",
        scenario_id=1,
        expert_attestation_id=attestation.id,
        uat_acceptance_id="uat-1",
        deployment_evidence_id="deployment-1",
        schema_version=version,
        snapshot_hash="5" * 64,
        release_hash="9" * 64,
        release_note="synthetic readiness fixture, never formal evidence",
        status="active",
        released_by=1,
        released_at=now,
        expires_at=now + timedelta(days=1),
    )
    db.add_all([compilation, proof, attestation, release])
    db.commit()


def test_empty_database_is_ready_and_does_not_write(readiness_db) -> None:
    report = build_version_readiness_report(
        readiness_db, environment="production"
    )
    assert report["status"] == "ready"
    assert report["ready"] is True
    assert report["enforced"] is True
    assert set(report["object_counts"].values()) == {0}
    assert report["checks"]["automatic_history_rewrite"] == "disabled"


def test_unknown_versions_warn_in_development_and_block_production(
    readiness_db,
) -> None:
    _add_versioned_rows(readiness_db, version="9.9")
    development = build_version_readiness_report(
        readiness_db, environment="development"
    )
    assert development["status"] == "warning"
    assert development["ready"] is False
    assert development["enforced"] is False
    assert development["warnings"]
    reason_codes = {item["reason_code"] for item in development["version_issues"]}
    assert {
        "compiler_version_unsupported",
        "coverage_proof_schema_unsupported",
        "delivery_snapshot_schema_unsupported",
        "delivery_release_schema_unsupported",
    }.issubset(reason_codes)

    production = build_version_readiness_report(
        readiness_db, environment="production"
    )
    assert production["status"] == "blocked"
    assert production["ready"] is False
    assert production["enforced"] is True
    assert production["warnings"] == []


def test_readiness_endpoint_enforces_only_production(
    readiness_db, monkeypatch: pytest.MonkeyPatch
) -> None:
    _add_versioned_rows(readiness_db, version="9.9")
    monkeypatch.setattr(
        system,
        "get_settings",
        lambda: SimpleNamespace(app_env="development", is_production=False),
    )
    response = system.readiness(readiness_db)
    assert response.status == "warning"
    assert response.ready is False

    monkeypatch.setattr(
        system,
        "get_settings",
        lambda: SimpleNamespace(app_env="production", is_production=True),
    )
    with pytest.raises(HTTPException) as exc:
        system.readiness(readiness_db)
    assert exc.value.status_code == 503
    assert exc.value.detail["status"] == "blocked"
