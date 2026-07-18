from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    text,
    event,
    inspect,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.core.database import Base


DELIVERY_EVIDENCE_KINDS = frozenset(
    {
        "oab_submission",
        "oab_verification_report",
        "iti_signature_artifact",
        "iti_validation_report",
        "uat_test_plan",
        "uat_test_evidence",
        "content_primary_signature",
        "content_primary_validation_report",
        "content_secondary_signature",
        "content_secondary_validation_report",
        "gold_dataset",
        "evaluation_policy",
        "evaluation_run",
        "build_artifact_descriptor",
        "build_artifact_receipt",
        "sbom",
        "security_report",
        "provenance",
        "runtime_probe",
        "config_schema",
    }
)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class DeliveryEvidenceObject(Base):
    """Immutable, content-addressed bytes supporting a delivery assertion."""

    __tablename__ = "delivery_evidence_objects"
    __table_args__ = (
        UniqueConstraint(
            "evidence_kind",
            "content_sha256",
            name="uq_delivery_evidence_kind_content_sha256",
        ),
        CheckConstraint(
            "evidence_kind IN ("
            "'oab_submission','oab_verification_report',"
            "'iti_signature_artifact','iti_validation_report',"
            "'uat_test_plan','uat_test_evidence',"
            "'content_primary_signature','content_primary_validation_report',"
            "'content_secondary_signature','content_secondary_validation_report',"
            "'gold_dataset','evaluation_policy','evaluation_run',"
            "'build_artifact_descriptor','build_artifact_receipt',"
            "'sbom','security_report','provenance',"
            "'runtime_probe','config_schema'"
            ")",
            name="ck_delivery_evidence_object_kind",
        ),
        CheckConstraint(
            "status IN ('available','revoked')",
            name="ck_delivery_evidence_object_status",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    scenario_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("investigation_scenarios.id"), index=True, nullable=True
    )
    evidence_kind: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    media_type: Mapped[str] = mapped_column(String(255), nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    content_length: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    source_url: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)
    status: Mapped[str] = mapped_column(String(24), index=True, nullable=False)
    uploaded_by: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), index=True, nullable=True
    )
    revoked_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    revocation_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )


class LegalExpertCredential(Base):
    """A human credential claim whose verification is an external, expiring fact."""

    __tablename__ = "legal_expert_credentials"
    __table_args__ = (
        UniqueConstraint(
            "authority", "registration_number", name="uq_legal_expert_authority_registration"
        ),
        CheckConstraint(
            "status IN ('pending','verified','rejected','revoked')",
            name="ck_legal_expert_credential_status",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    holder_name: Mapped[str] = mapped_column(String(255), nullable=False)
    jurisdiction: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    authority: Mapped[str] = mapped_column(String(255), nullable=False)
    registration_number: Mapped[str] = mapped_column(String(128), nullable=False)
    official_register_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    submitted_evidence_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(24), index=True, nullable=False)
    verification_reference: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)
    verification_evidence_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    registration_status: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    decision_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    verified_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    valid_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    revision: Mapped[int] = mapped_column(
        Integer, default=0, server_default=text("0"), nullable=False
    )
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class ScenarioExpertAttestation(Base):
    """Immutable legal sign-off over one machine-recomputable scenario snapshot."""

    __tablename__ = "scenario_expert_attestations"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending_validation','active','superseded','rejected','revoked')",
            name="ck_scenario_expert_attestation_status",
        ),
        CheckConstraint(
            "signature_validation_status IN ('submitted','approved','rejected')",
            name="ck_expert_signature_validation_status",
        ),
        Index(
            "uq_scenario_expert_attestation_active",
            "scenario_id",
            unique=True,
            postgresql_where=text("status = 'active'"),
            sqlite_where=text("status = 'active'"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    scenario_id: Mapped[int] = mapped_column(
        ForeignKey("investigation_scenarios.id"), index=True, nullable=False
    )
    credential_id: Mapped[str] = mapped_column(
        ForeignKey("legal_expert_credentials.id"), index=True, nullable=False
    )
    signed_by: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    snapshot_hash: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    artifact_manifest: Mapped[list] = mapped_column(JSON, nullable=False)
    artifact_manifest_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    signature_format: Mapped[str] = mapped_column(String(32), nullable=False)
    signature_artifact_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    signature_validation_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    signature_validation_report_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    signature_validation_status: Mapped[str] = mapped_column(String(24), nullable=False)
    signature_verified_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    signature_verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    signature_verification_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    certificate_subject: Mapped[str] = mapped_column(String(512), nullable=False)
    certificate_serial: Mapped[str] = mapped_column(String(255), nullable=False)
    certificate_valid_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    limitations: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(24), index=True, nullable=False)
    signed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    revoked_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    revocation_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class ScenarioUATAcceptance(Base):
    """Customer acceptance over the same snapshot signed by the scenario owner."""

    __tablename__ = "scenario_uat_acceptances"
    __table_args__ = (
        CheckConstraint(
            "status IN ('accepted','superseded','withdrawn')",
            name="ck_scenario_uat_acceptance_status",
        ),
        Index(
            "uq_scenario_uat_acceptance_accepted",
            "scenario_id",
            unique=True,
            postgresql_where=text("status = 'accepted'"),
            sqlite_where=text("status = 'accepted'"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    scenario_id: Mapped[int] = mapped_column(
        ForeignKey("investigation_scenarios.id"), index=True, nullable=False
    )
    expert_attestation_id: Mapped[str] = mapped_column(
        ForeignKey("scenario_expert_attestations.id"), index=True, nullable=False
    )
    accepted_by: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    customer_organization: Mapped[str] = mapped_column(String(255), nullable=False)
    snapshot_hash: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    test_plan_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    test_evidence_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    evidence_reference: Mapped[str] = mapped_column(String(2048), nullable=False)
    environment: Mapped[str] = mapped_column(String(64), nullable=False)
    target_environment_id: Mapped[str] = mapped_column(String(255), nullable=False)
    acceptance_statement: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(24), index=True, nullable=False)
    accepted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    withdrawn_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    withdrawal_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class ScenarioDeliveryArtifact(Base):
    """Frozen customer bytes produced before signature and returned unchanged after release."""

    __tablename__ = "scenario_delivery_artifacts"
    __table_args__ = (
        CheckConstraint(
            "artifact_type IN ('docx','pdf','audit_bundle')",
            name="ck_scenario_delivery_artifact_type",
        ),
        CheckConstraint(
            "status IN ('candidate','superseded','released','revoked')",
            name="ck_scenario_delivery_artifact_status",
        ),
        Index(
            "uq_scenario_delivery_artifact_candidate_type",
            "scenario_id",
            "artifact_type",
            unique=True,
            postgresql_where=text("status = 'candidate'"),
            sqlite_where=text("status = 'candidate'"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    scenario_id: Mapped[int] = mapped_column(
        ForeignKey("investigation_scenarios.id"), index=True, nullable=False
    )
    artifact_type: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    snapshot_hash: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    content_length: Mapped[int] = mapped_column(Integer, nullable=False)
    media_type: Mapped[str] = mapped_column(String(255), nullable=False)
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    renderer_version: Mapped[str] = mapped_column(String(128), nullable=False)
    content: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    status: Mapped[str] = mapped_column(String(24), index=True, nullable=False)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class LegalContentCertification(Base):
    """Two-expert certification of one exact rules/corpus/gold release."""

    __tablename__ = "legal_content_certifications"
    __table_args__ = (
        CheckConstraint(
            "status IN ('certified','revoked')", name="ck_legal_content_certification_status"
        ),
        CheckConstraint(
            "regression_status = 'passed'", name="ck_legal_content_regression_passed"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    capability_pack_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    capability_pack_version: Mapped[str] = mapped_column(String(64), nullable=False)
    capability_pack_hash: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    rules_artifact_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    corpus_artifact_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    gold_dataset_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    evaluation_policy_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    evaluation_run_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    regression_status: Mapped[str] = mapped_column(String(24), nullable=False)
    primary_credential_id: Mapped[str] = mapped_column(
        ForeignKey("legal_expert_credentials.id"), index=True, nullable=False
    )
    secondary_credential_id: Mapped[str] = mapped_column(
        ForeignKey("legal_expert_credentials.id"), index=True, nullable=False
    )
    primary_signature_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    primary_certificate_subject: Mapped[str] = mapped_column(String(512), nullable=False)
    primary_certificate_serial: Mapped[str] = mapped_column(String(255), nullable=False)
    primary_validation_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    primary_validation_report_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    secondary_signature_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    secondary_certificate_subject: Mapped[str] = mapped_column(String(512), nullable=False)
    secondary_certificate_serial: Mapped[str] = mapped_column(String(255), nullable=False)
    secondary_validation_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    secondary_validation_report_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    certification_manifest_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    limitations: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(24), index=True, nullable=False)
    certified_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    certified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    revoked_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    revocation_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class DeploymentEvidence(Base):
    """Admin-verified production build evidence; never inferred from the running process."""

    __tablename__ = "deployment_evidence"
    __table_args__ = (
        CheckConstraint(
            "environment IN ('staging','production')", name="ck_deployment_environment"
        ),
        CheckConstraint(
            "status IN ('verified','revoked')", name="ck_deployment_evidence_status"
        ),
        CheckConstraint(
            "regression_status = 'passed'", name="ck_deployment_regression_passed"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    legal_content_certification_id: Mapped[str] = mapped_column(
        ForeignKey("legal_content_certifications.id"), index=True, nullable=False
    )
    environment: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    target_environment_id: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    commit_sha: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    migration_head: Mapped[str] = mapped_column(String(128), nullable=False)
    ci_run_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    artifact_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    artifact_receipt_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    sbom_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    security_evidence_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    security_evidence_sha256: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    provenance_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    provenance_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    runtime_probe_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    runtime_probe_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    backend_image_digest: Mapped[str] = mapped_column(String(71), nullable=False)
    frontend_image_digest: Mapped[str] = mapped_column(String(71), nullable=False)
    database_image_digest: Mapped[str] = mapped_column(String(71), nullable=False)
    config_schema_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    capability_pack_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    rules_artifact_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    corpus_artifact_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    gold_dataset_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    evaluation_policy_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    evaluation_run_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    regression_status: Mapped[str] = mapped_column(String(24), nullable=False)
    verification_note: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(24), index=True, nullable=False)
    verified_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    revoked_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    revocation_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class ScenarioDeliveryRelease(Base):
    """Final, revocable authorization binding expert, customer and deployment evidence."""

    __tablename__ = "scenario_delivery_releases"
    __table_args__ = (
        UniqueConstraint("release_hash"),
        CheckConstraint(
            "status IN ('active','superseded','revoked')",
            name="ck_scenario_delivery_release_status",
        ),
        Index(
            "uq_scenario_delivery_release_active",
            "scenario_id",
            unique=True,
            postgresql_where=text("status = 'active'"),
            sqlite_where=text("status = 'active'"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    scenario_id: Mapped[int] = mapped_column(
        ForeignKey("investigation_scenarios.id"), index=True, nullable=False
    )
    expert_attestation_id: Mapped[str] = mapped_column(
        ForeignKey("scenario_expert_attestations.id"), index=True, nullable=False
    )
    uat_acceptance_id: Mapped[str] = mapped_column(
        ForeignKey("scenario_uat_acceptances.id"), index=True, nullable=False
    )
    deployment_evidence_id: Mapped[str] = mapped_column(
        ForeignKey("deployment_evidence.id"), index=True, nullable=False
    )
    snapshot_hash: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    release_hash: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    release_note: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(24), index=True, nullable=False)
    released_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    released_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    revoked_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    revocation_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


_MUTABLE_FIELDS = {
    DeliveryEvidenceObject: {"status", "revoked_by", "revoked_at", "revocation_reason"},
    LegalExpertCredential: {
        "status",
        "verification_reference",
        "verification_evidence_hash",
        "registration_status",
        "decision_note",
        "verified_by",
        "verified_at",
        "valid_until",
        "revoked_by",
        "revoked_at",
        "revision",
        "updated_at",
    },
    ScenarioExpertAttestation: {
        "status",
        "signature_validation_status",
        "signature_verified_by",
        "signature_verified_at",
        "signature_verification_note",
        "revoked_by",
        "revoked_at",
        "revocation_reason",
    },
    ScenarioUATAcceptance: {
        "status",
        "withdrawn_at",
        "withdrawal_reason",
    },
    ScenarioDeliveryArtifact: {"status"},
    LegalContentCertification: {"status", "revoked_by", "revoked_at", "revocation_reason"},
    DeploymentEvidence: {"status", "revoked_by", "revoked_at", "revocation_reason"},
    ScenarioDeliveryRelease: {"status", "revoked_by", "revoked_at", "revocation_reason"},
}


def _protect_immutable_core(_mapper, _connection, target) -> None:
    allowed = _MUTABLE_FIELDS[type(target)]
    changed = {
        attribute.key
        for attribute in inspect(target).attrs
        if attribute.history.has_changes()
    }
    forbidden = sorted(changed - allowed)
    if forbidden:
        raise ValueError(
            f"delivery assurance immutable core cannot be updated: {', '.join(forbidden)}"
        )


def _prevent_delivery_delete(_mapper, _connection, target) -> None:
    raise ValueError(f"delivery assurance evidence cannot be deleted: {type(target).__name__}")


for _model in _MUTABLE_FIELDS:
    event.listen(_model, "before_update", _protect_immutable_core)
    event.listen(_model, "before_delete", _prevent_delivery_delete)
