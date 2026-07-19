"""Read-only startup/readiness audit for every persisted version identity."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models.delivery_assurance import ScenarioDeliveryRelease, ScenarioExpertAttestation
from app.models.mechanism import ClaimCompilation, CoverageProof
from app.services.versioned import registry


def _version(value: object) -> str:
    return value if isinstance(value, str) and value else "<missing>"


def _issue(unit: str, version: object, object_id: object, reason_code: str) -> dict[str, str]:
    return {
        "unit": unit,
        "version": _version(version),
        "object_id": str(object_id),
        "reason_code": reason_code,
    }


def build_version_readiness_report(
    db: Session,
    *,
    environment: str,
) -> dict[str, Any]:
    """Scan identities without mutating, repairing or reserializing any row."""

    registry_errors: list[str] = []
    try:
        registry.validate_registry_configuration(
            compiler_readers=registry.SUPPORTED_COMPILER_READERS,
            proof_readers=registry.SUPPORTED_COVERAGE_PROOF_READERS,
            combinations=registry.SUPPORTED_COMPILER_PROOF_COMBINATIONS,
            current_compiler_write_version=registry.CURRENT_COMPILER_WRITE_VERSION,
            current_proof_write_version=registry.CURRENT_COVERAGE_PROOF_WRITE_VERSION,
        )
        registry.validate_delivery_registry_configuration()
    except registry.VersionedRegistryError as exc:
        registry_errors.append(str(exc))

    issues: list[dict[str, str]] = []
    counts = {
        "claim_compilations": 0,
        "coverage_proofs": 0,
        "delivery_snapshots": 0,
        "delivery_releases": 0,
    }

    for compilation_id, compiler_version in db.query(
        ClaimCompilation.id, ClaimCompilation.compiler_version
    ).yield_per(500):
        counts["claim_compilations"] += 1
        if compiler_version not in registry.SUPPORTED_COMPILER_READERS:
            issues.append(
                _issue(
                    "claim_compiler",
                    compiler_version,
                    compilation_id,
                    "compiler_version_unsupported",
                )
            )

    proof_rows = db.query(
        CoverageProof.id,
        CoverageProof.proof,
        ClaimCompilation.compiler_version,
    ).outerjoin(
        ClaimCompilation, ClaimCompilation.id == CoverageProof.compilation_id
    )
    for proof_id, proof_body, compiler_version in proof_rows.yield_per(500):
        counts["coverage_proofs"] += 1
        proof_version = proof_body.get("schema_version") if isinstance(proof_body, dict) else None
        if proof_version not in registry.SUPPORTED_COVERAGE_PROOF_READERS:
            issues.append(
                _issue(
                    "coverage_proof",
                    proof_version,
                    proof_id,
                    "coverage_proof_schema_unsupported",
                )
            )
        elif (
            compiler_version,
            proof_version,
        ) not in registry.SUPPORTED_COMPILER_PROOF_COMBINATIONS:
            issues.append(
                _issue(
                    "compiler_proof_combination",
                    f"{_version(compiler_version)}+{proof_version}",
                    proof_id,
                    "version_combination_unsupported",
                )
            )

    for attestation_id, snapshot in db.query(
        ScenarioExpertAttestation.id, ScenarioExpertAttestation.snapshot
    ).yield_per(500):
        counts["delivery_snapshots"] += 1
        snapshot_version = snapshot.get("schema_version") if isinstance(snapshot, dict) else None
        if snapshot_version not in registry.SUPPORTED_DELIVERY_SNAPSHOT_READERS:
            issues.append(
                _issue(
                    "delivery_snapshot",
                    snapshot_version,
                    attestation_id,
                    "delivery_snapshot_schema_unsupported",
                )
            )

    for release_id, release_version in db.query(
        ScenarioDeliveryRelease.id, ScenarioDeliveryRelease.schema_version
    ).yield_per(500):
        counts["delivery_releases"] += 1
        if release_version not in registry.SUPPORTED_DELIVERY_RELEASE_READERS:
            issues.append(
                _issue(
                    "delivery_release",
                    release_version,
                    release_id,
                    "delivery_release_schema_unsupported",
                )
            )

    is_production = environment.strip().lower() == "production"
    ready = not registry_errors and not issues
    status = "ready" if ready else ("blocked" if is_production else "warning")
    warnings = [
        "development_readiness_warning: persisted unknown versions remain fail-closed at use time"
    ] if issues and not is_production else []
    return {
        "schema_version": "1.0",
        "status": status,
        "ready": ready,
        "enforced": is_production,
        "environment": environment,
        "checks": {
            "required_historical_readers": "passed" if not registry_errors else "failed",
            "current_writers_registered": "passed" if not registry_errors else "failed",
            "compatibility_matrix_closed": "passed" if not registry_errors else "failed",
            "persisted_versions_supported": "passed" if not issues else "failed",
            "automatic_history_rewrite": "disabled",
        },
        "object_counts": counts,
        "registry_errors": registry_errors,
        "version_issues": issues,
        "warnings": warnings,
    }
