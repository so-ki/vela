"""Frozen delivery release 1.1 body and evidence serialization."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.services.versioned.canonical_hash.v1 import canonical_hash_v1

VERSION = "1.1"


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _iso(value: datetime | None) -> str | None:
    return _as_utc(value).isoformat() if value else None


def hash_payload(payload: Any) -> str:
    return canonical_hash_v1(payload)


def credential_evidence(credential: Any) -> dict[str, Any]:
    return {
        "id": credential.id,
        "user_id": credential.user_id,
        "holder_name": credential.holder_name,
        "jurisdiction": credential.jurisdiction,
        "authority": credential.authority,
        "registration_number": credential.registration_number,
        "official_register_url": credential.official_register_url,
        "submitted_evidence_hash": credential.submitted_evidence_hash,
        "verification_reference": credential.verification_reference,
        "verification_evidence_hash": credential.verification_evidence_hash,
        "registration_status": credential.registration_status,
        "decision_note": credential.decision_note,
        "status": credential.status,
        "revision": credential.revision,
        "verified_by": credential.verified_by,
        "verified_at": _iso(credential.verified_at),
        "valid_until": _iso(credential.valid_until),
    }


def attestation_evidence(attestation: Any) -> dict[str, Any]:
    return {
        "id": attestation.id,
        "scenario_id": attestation.scenario_id,
        "credential_id": attestation.credential_id,
        "signed_by": attestation.signed_by,
        "snapshot_hash": attestation.snapshot_hash,
        "artifact_manifest_hash": attestation.artifact_manifest_hash,
        "signature_format": attestation.signature_format,
        "signature_artifact_hash": attestation.signature_artifact_hash,
        "signature_validation_url": attestation.signature_validation_url,
        "signature_validation_report_hash": attestation.signature_validation_report_hash,
        "signature_validation_status": attestation.signature_validation_status,
        "signature_verified_by": attestation.signature_verified_by,
        "signature_verified_at": _iso(attestation.signature_verified_at),
        "signature_verification_note": attestation.signature_verification_note,
        "certificate_subject": attestation.certificate_subject,
        "certificate_serial": attestation.certificate_serial,
        "certificate_valid_until": _iso(attestation.certificate_valid_until),
        "statement": attestation.statement,
        "limitations": attestation.limitations,
        "status": attestation.status,
        "signed_at": _iso(attestation.signed_at),
        "expires_at": _iso(attestation.expires_at),
    }


def uat_evidence(acceptance: Any) -> dict[str, Any]:
    return {
        "id": acceptance.id,
        "scenario_id": acceptance.scenario_id,
        "expert_attestation_id": acceptance.expert_attestation_id,
        "accepted_by": acceptance.accepted_by,
        "customer_organization": acceptance.customer_organization,
        "snapshot_hash": acceptance.snapshot_hash,
        "test_plan_hash": acceptance.test_plan_hash,
        "test_evidence_hash": acceptance.test_evidence_hash,
        "evidence_reference": acceptance.evidence_reference,
        "environment": acceptance.environment,
        "target_environment_id": acceptance.target_environment_id,
        "acceptance_statement": acceptance.acceptance_statement,
        "status": acceptance.status,
        "accepted_at": _iso(acceptance.accepted_at),
        "expires_at": _iso(acceptance.expires_at),
    }


def content_certification_evidence(certification: Any) -> dict[str, Any]:
    return {
        "id": certification.id,
        "manifest_hash": certification.certification_manifest_hash,
        "primary_credential_id": certification.primary_credential_id,
        "secondary_credential_id": certification.secondary_credential_id,
        "primary_signature_hash": certification.primary_signature_hash,
        "primary_certificate_subject": certification.primary_certificate_subject,
        "primary_certificate_serial": certification.primary_certificate_serial,
        "primary_validation_url": certification.primary_validation_url,
        "primary_validation_report_hash": certification.primary_validation_report_hash,
        "secondary_signature_hash": certification.secondary_signature_hash,
        "secondary_certificate_subject": certification.secondary_certificate_subject,
        "secondary_certificate_serial": certification.secondary_certificate_serial,
        "secondary_validation_url": certification.secondary_validation_url,
        "secondary_validation_report_hash": certification.secondary_validation_report_hash,
        "status": certification.status,
        "certified_by": certification.certified_by,
        "certified_at": _iso(certification.certified_at),
        "expires_at": _iso(certification.expires_at),
    }


def deployment_evidence_manifest(deployment: Any) -> dict[str, Any]:
    fields = (
        "id", "legal_content_certification_id", "environment",
        "target_environment_id", "commit_sha", "migration_head", "ci_run_url",
        "artifact_sha256", "artifact_receipt_hash", "sbom_sha256",
        "security_evidence_url", "security_evidence_sha256", "provenance_url",
        "provenance_sha256", "runtime_probe_url", "runtime_probe_sha256",
        "backend_image_digest", "frontend_image_digest", "database_image_digest",
        "config_schema_sha256", "capability_pack_hash", "rules_artifact_hash",
        "corpus_artifact_hash", "gold_dataset_sha256", "evaluation_policy_sha256",
        "evaluation_run_sha256", "regression_status", "verification_note",
        "status", "verified_by",
    )
    result = {field: getattr(deployment, field) for field in fields}
    result.update({"verified_at": _iso(deployment.verified_at), "expires_at": _iso(deployment.expires_at)})
    return result


def delivery_evidence_manifest(evidence_objects: list[Any]) -> list[dict[str, Any]]:
    return [
        {
            "id": item.id,
            "scenario_id": item.scenario_id,
            "evidence_kind": item.evidence_kind,
            "filename": item.filename,
            "media_type": item.media_type,
            "content_sha256": item.content_sha256,
            "content_length": item.content_length,
            "source_url": item.source_url,
            "status": item.status,
            "uploaded_by": item.uploaded_by,
            "uploaded_at": _iso(item.uploaded_at),
            "expires_at": _iso(item.expires_at),
        }
        for item in sorted(evidence_objects, key=lambda value: value.id)
    ]


def build_release_body(
    *, scenario_id: int, snapshot_hash: str, attestation: Any, acceptance: Any,
    deployment: Any, content_certification: Any, scenario_credential: Any,
    primary_credential: Any, secondary_credential: Any,
    evidence_objects: list[Any], release_note: str, released_by: int,
    released_at: datetime, expires_at: datetime,
) -> dict[str, Any]:
    return {
        "schema_version": VERSION,
        "scenario_id": scenario_id,
        "snapshot_hash": snapshot_hash,
        "expert_attestation_id": attestation.id,
        "expert_attestation_evidence_hash": hash_payload(attestation_evidence(attestation)),
        "artifact_manifest_hash": attestation.artifact_manifest_hash,
        "uat_acceptance_id": acceptance.id,
        "uat_evidence_hash": hash_payload(uat_evidence(acceptance)),
        "deployment_evidence_id": deployment.id,
        "deployment_evidence_hash": hash_payload(deployment_evidence_manifest(deployment)),
        "legal_content_certification_id": content_certification.id,
        "legal_content_certification_evidence_hash": hash_payload(content_certification_evidence(content_certification)),
        "scenario_credential_evidence_hash": hash_payload(credential_evidence(scenario_credential)),
        "primary_content_credential_evidence_hash": hash_payload(credential_evidence(primary_credential)),
        "secondary_content_credential_evidence_hash": hash_payload(credential_evidence(secondary_credential)),
        "delivery_evidence_manifest_hash": hash_payload(delivery_evidence_manifest(evidence_objects)),
        "release_note_hash": hash_payload({"release_note": release_note.strip()}),
        "released_by": released_by,
        "released_at": _as_utc(released_at).isoformat(),
        "expires_at": _as_utc(expires_at).isoformat(),
    }
