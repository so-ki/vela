"""Add fail-closed customer delivery assurance evidence chain.

Revision ID: 20260718_0005
Revises: 20260717_0004
Create Date: 2026-07-18
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260718_0005"
down_revision: Union[str, None] = "20260717_0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _active_unique(name: str, table: str, columns: list[str], predicate: str) -> None:
    op.create_index(
        name,
        table,
        columns,
        unique=True,
        postgresql_where=sa.text(predicate),
        sqlite_where=sa.text(predicate),
    )


def upgrade() -> None:
    op.create_table(
        "legal_expert_credentials",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("holder_name", sa.String(length=255), nullable=False),
        sa.Column("jurisdiction", sa.String(length=64), nullable=False),
        sa.Column("authority", sa.String(length=255), nullable=False),
        sa.Column("registration_number", sa.String(length=128), nullable=False),
        sa.Column("official_register_url", sa.String(length=2048), nullable=False),
        sa.Column("submitted_evidence_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("verification_reference", sa.String(length=2048), nullable=True),
        sa.Column("verification_evidence_hash", sa.String(length=64), nullable=True),
        sa.Column("registration_status", sa.String(length=64), nullable=True),
        sa.Column("decision_note", sa.Text(), nullable=True),
        sa.Column("verified_by", sa.Integer(), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_by", sa.Integer(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revision", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending','verified','rejected','revoked')",
            name="ck_legal_expert_credential_status",
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["revoked_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["verified_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "authority", "registration_number", name="uq_legal_expert_authority_registration"
        ),
    )
    op.create_index("ix_legal_expert_credentials_user_id", "legal_expert_credentials", ["user_id"])
    op.create_index(
        "ix_legal_expert_credentials_jurisdiction",
        "legal_expert_credentials",
        ["jurisdiction"],
    )
    op.create_index("ix_legal_expert_credentials_status", "legal_expert_credentials", ["status"])

    op.create_table(
        "scenario_expert_attestations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("scenario_id", sa.Integer(), nullable=False),
        sa.Column("credential_id", sa.String(length=36), nullable=False),
        sa.Column("signed_by", sa.Integer(), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("snapshot_hash", sa.String(length=64), nullable=False),
        sa.Column("artifact_manifest", sa.JSON(), nullable=False),
        sa.Column("artifact_manifest_hash", sa.String(length=64), nullable=False),
        sa.Column("signature_format", sa.String(length=32), nullable=False),
        sa.Column("signature_artifact_hash", sa.String(length=64), nullable=False),
        sa.Column("signature_validation_url", sa.String(length=2048), nullable=False),
        sa.Column("signature_validation_report_hash", sa.String(length=64), nullable=False),
        sa.Column("signature_validation_status", sa.String(length=24), nullable=False),
        sa.Column("signature_verified_by", sa.Integer(), nullable=True),
        sa.Column("signature_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("signature_verification_note", sa.Text(), nullable=True),
        sa.Column("certificate_subject", sa.String(length=512), nullable=False),
        sa.Column("certificate_serial", sa.String(length=255), nullable=False),
        sa.Column("certificate_valid_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column("statement", sa.Text(), nullable=False),
        sa.Column("limitations", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("signed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_by", sa.Integer(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revocation_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending_validation','active','superseded','rejected','revoked')",
            name="ck_scenario_expert_attestation_status",
        ),
        sa.CheckConstraint(
            "signature_validation_status IN ('submitted','approved','rejected')",
            name="ck_expert_signature_validation_status",
        ),
        sa.ForeignKeyConstraint(["credential_id"], ["legal_expert_credentials.id"]),
        sa.ForeignKeyConstraint(["revoked_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["scenario_id"], ["investigation_scenarios.id"]),
        sa.ForeignKeyConstraint(["signature_verified_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["signed_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    for name, column in (
        ("scenario_id", "scenario_id"),
        ("credential_id", "credential_id"),
        ("signed_by", "signed_by"),
        ("snapshot_hash", "snapshot_hash"),
        ("status", "status"),
        ("expires_at", "expires_at"),
    ):
        op.create_index(
            f"ix_scenario_expert_attestations_{name}", "scenario_expert_attestations", [column]
        )
    _active_unique(
        "uq_scenario_expert_attestation_active",
        "scenario_expert_attestations",
        ["scenario_id"],
        "status = 'active'",
    )

    op.create_table(
        "scenario_uat_acceptances",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("scenario_id", sa.Integer(), nullable=False),
        sa.Column("expert_attestation_id", sa.String(length=36), nullable=False),
        sa.Column("accepted_by", sa.Integer(), nullable=False),
        sa.Column("customer_organization", sa.String(length=255), nullable=False),
        sa.Column("snapshot_hash", sa.String(length=64), nullable=False),
        sa.Column("test_plan_hash", sa.String(length=64), nullable=False),
        sa.Column("test_evidence_hash", sa.String(length=64), nullable=False),
        sa.Column("evidence_reference", sa.String(length=2048), nullable=False),
        sa.Column("environment", sa.String(length=64), nullable=False),
        sa.Column("target_environment_id", sa.String(length=255), nullable=False),
        sa.Column("acceptance_statement", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("withdrawn_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("withdrawal_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('accepted','superseded','withdrawn')",
            name="ck_scenario_uat_acceptance_status",
        ),
        sa.ForeignKeyConstraint(["accepted_by"], ["users.id"]),
        sa.ForeignKeyConstraint(
            ["expert_attestation_id"], ["scenario_expert_attestations.id"]
        ),
        sa.ForeignKeyConstraint(["scenario_id"], ["investigation_scenarios.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    for name in ("scenario_id", "expert_attestation_id", "accepted_by", "snapshot_hash", "status", "expires_at"):
        op.create_index(f"ix_scenario_uat_acceptances_{name}", "scenario_uat_acceptances", [name])
    _active_unique(
        "uq_scenario_uat_acceptance_accepted",
        "scenario_uat_acceptances",
        ["scenario_id"],
        "status = 'accepted'",
    )

    op.create_table(
        "scenario_delivery_artifacts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("scenario_id", sa.Integer(), nullable=False),
        sa.Column("artifact_type", sa.String(length=32), nullable=False),
        sa.Column("snapshot_hash", sa.String(length=64), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("content_length", sa.Integer(), nullable=False),
        sa.Column("media_type", sa.String(length=255), nullable=False),
        sa.Column("filename", sa.String(length=512), nullable=False),
        sa.Column("renderer_version", sa.String(length=128), nullable=False),
        sa.Column("content", sa.LargeBinary(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "artifact_type IN ('docx','pdf','audit_bundle')",
            name="ck_scenario_delivery_artifact_type",
        ),
        sa.CheckConstraint(
            "status IN ('candidate','superseded','released','revoked')",
            name="ck_scenario_delivery_artifact_status",
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["scenario_id"], ["investigation_scenarios.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    for name in ("scenario_id", "artifact_type", "snapshot_hash", "content_sha256", "status"):
        op.create_index(f"ix_scenario_delivery_artifacts_{name}", "scenario_delivery_artifacts", [name])
    _active_unique(
        "uq_scenario_delivery_artifact_candidate_type",
        "scenario_delivery_artifacts",
        ["scenario_id", "artifact_type"],
        "status = 'candidate'",
    )

    op.create_table(
        "legal_content_certifications",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("capability_pack_id", sa.String(length=128), nullable=False),
        sa.Column("capability_pack_version", sa.String(length=64), nullable=False),
        sa.Column("capability_pack_hash", sa.String(length=64), nullable=False),
        sa.Column("rules_artifact_hash", sa.String(length=64), nullable=False),
        sa.Column("corpus_artifact_hash", sa.String(length=64), nullable=False),
        sa.Column("gold_dataset_sha256", sa.String(length=64), nullable=False),
        sa.Column("evaluation_policy_sha256", sa.String(length=64), nullable=False),
        sa.Column("evaluation_run_sha256", sa.String(length=64), nullable=False),
        sa.Column("regression_status", sa.String(length=24), nullable=False),
        sa.Column("primary_credential_id", sa.String(length=36), nullable=False),
        sa.Column("secondary_credential_id", sa.String(length=36), nullable=False),
        sa.Column("primary_signature_hash", sa.String(length=64), nullable=False),
        sa.Column("primary_certificate_subject", sa.String(length=512), nullable=False),
        sa.Column("primary_certificate_serial", sa.String(length=255), nullable=False),
        sa.Column("primary_validation_url", sa.String(length=2048), nullable=False),
        sa.Column("primary_validation_report_hash", sa.String(length=64), nullable=False),
        sa.Column("secondary_signature_hash", sa.String(length=64), nullable=False),
        sa.Column("secondary_certificate_subject", sa.String(length=512), nullable=False),
        sa.Column("secondary_certificate_serial", sa.String(length=255), nullable=False),
        sa.Column("secondary_validation_url", sa.String(length=2048), nullable=False),
        sa.Column("secondary_validation_report_hash", sa.String(length=64), nullable=False),
        sa.Column("certification_manifest_hash", sa.String(length=64), nullable=False),
        sa.Column("limitations", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("certified_by", sa.Integer(), nullable=False),
        sa.Column("certified_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_by", sa.Integer(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revocation_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('certified','revoked')", name="ck_legal_content_certification_status"
        ),
        sa.CheckConstraint(
            "regression_status = 'passed'", name="ck_legal_content_regression_passed"
        ),
        sa.ForeignKeyConstraint(["certified_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["primary_credential_id"], ["legal_expert_credentials.id"]),
        sa.ForeignKeyConstraint(["revoked_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["secondary_credential_id"], ["legal_expert_credentials.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("certification_manifest_hash"),
    )
    for name in (
        "capability_pack_id",
        "capability_pack_hash",
        "primary_credential_id",
        "secondary_credential_id",
        "status",
        "expires_at",
    ):
        op.create_index(
            f"ix_legal_content_certifications_{name}", "legal_content_certifications", [name]
        )

    op.create_table(
        "deployment_evidence",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("legal_content_certification_id", sa.String(length=36), nullable=False),
        sa.Column("environment", sa.String(length=32), nullable=False),
        sa.Column("target_environment_id", sa.String(length=255), nullable=False),
        sa.Column("commit_sha", sa.String(length=64), nullable=False),
        sa.Column("migration_head", sa.String(length=128), nullable=False),
        sa.Column("ci_run_url", sa.String(length=2048), nullable=False),
        sa.Column("artifact_sha256", sa.String(length=64), nullable=False),
        sa.Column("sbom_sha256", sa.String(length=64), nullable=False),
        sa.Column("security_evidence_url", sa.String(length=2048), nullable=False),
        sa.Column("provenance_url", sa.String(length=2048), nullable=False),
        sa.Column("provenance_sha256", sa.String(length=64), nullable=False),
        sa.Column("runtime_probe_url", sa.String(length=2048), nullable=False),
        sa.Column("runtime_probe_sha256", sa.String(length=64), nullable=False),
        sa.Column("backend_image_digest", sa.String(length=71), nullable=False),
        sa.Column("frontend_image_digest", sa.String(length=71), nullable=False),
        sa.Column("database_image_digest", sa.String(length=71), nullable=False),
        sa.Column("config_schema_sha256", sa.String(length=64), nullable=False),
        sa.Column("capability_pack_hash", sa.String(length=64), nullable=False),
        sa.Column("rules_artifact_hash", sa.String(length=64), nullable=False),
        sa.Column("corpus_artifact_hash", sa.String(length=64), nullable=False),
        sa.Column("gold_dataset_sha256", sa.String(length=64), nullable=False),
        sa.Column("evaluation_policy_sha256", sa.String(length=64), nullable=False),
        sa.Column("evaluation_run_sha256", sa.String(length=64), nullable=False),
        sa.Column("regression_status", sa.String(length=24), nullable=False),
        sa.Column("verification_note", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("verified_by", sa.Integer(), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_by", sa.Integer(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revocation_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("environment IN ('staging','production')", name="ck_deployment_environment"),
        sa.CheckConstraint("status IN ('verified','revoked')", name="ck_deployment_evidence_status"),
        sa.CheckConstraint("regression_status = 'passed'", name="ck_deployment_regression_passed"),
        sa.ForeignKeyConstraint(["revoked_by"], ["users.id"]),
        sa.ForeignKeyConstraint(
            ["legal_content_certification_id"], ["legal_content_certifications.id"]
        ),
        sa.ForeignKeyConstraint(["verified_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    for name in (
        "legal_content_certification_id",
        "environment",
        "target_environment_id",
        "commit_sha",
        "status",
        "expires_at",
    ):
        op.create_index(f"ix_deployment_evidence_{name}", "deployment_evidence", [name])

    op.create_table(
        "scenario_delivery_releases",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("scenario_id", sa.Integer(), nullable=False),
        sa.Column("expert_attestation_id", sa.String(length=36), nullable=False),
        sa.Column("uat_acceptance_id", sa.String(length=36), nullable=False),
        sa.Column("deployment_evidence_id", sa.String(length=36), nullable=False),
        sa.Column("snapshot_hash", sa.String(length=64), nullable=False),
        sa.Column("release_hash", sa.String(length=64), nullable=False),
        sa.Column("release_note", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("released_by", sa.Integer(), nullable=False),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_by", sa.Integer(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revocation_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('active','superseded','revoked')",
            name="ck_scenario_delivery_release_status",
        ),
        sa.ForeignKeyConstraint(["deployment_evidence_id"], ["deployment_evidence.id"]),
        sa.ForeignKeyConstraint(["expert_attestation_id"], ["scenario_expert_attestations.id"]),
        sa.ForeignKeyConstraint(["released_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["revoked_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["scenario_id"], ["investigation_scenarios.id"]),
        sa.ForeignKeyConstraint(["uat_acceptance_id"], ["scenario_uat_acceptances.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("release_hash"),
    )
    for name in (
        "scenario_id",
        "expert_attestation_id",
        "uat_acceptance_id",
        "deployment_evidence_id",
        "snapshot_hash",
        "release_hash",
        "status",
        "expires_at",
    ):
        op.create_index(f"ix_scenario_delivery_releases_{name}", "scenario_delivery_releases", [name])
    _active_unique(
        "uq_scenario_delivery_release_active",
        "scenario_delivery_releases",
        ["scenario_id"],
        "status = 'active'",
    )


def downgrade() -> None:
    op.drop_index("uq_scenario_delivery_release_active", table_name="scenario_delivery_releases")
    for name in reversed(
        (
            "scenario_id",
            "expert_attestation_id",
            "uat_acceptance_id",
            "deployment_evidence_id",
            "snapshot_hash",
            "release_hash",
            "status",
            "expires_at",
        )
    ):
        op.drop_index(f"ix_scenario_delivery_releases_{name}", table_name="scenario_delivery_releases")
    op.drop_table("scenario_delivery_releases")
    for name in reversed(
        (
            "legal_content_certification_id",
            "environment",
            "target_environment_id",
            "commit_sha",
            "status",
            "expires_at",
        )
    ):
        op.drop_index(f"ix_deployment_evidence_{name}", table_name="deployment_evidence")
    op.drop_table("deployment_evidence")
    for name in reversed(
        (
            "capability_pack_id",
            "capability_pack_hash",
            "primary_credential_id",
            "secondary_credential_id",
            "status",
            "expires_at",
        )
    ):
        op.drop_index(
            f"ix_legal_content_certifications_{name}",
            table_name="legal_content_certifications",
        )
    op.drop_table("legal_content_certifications")
    op.drop_index("uq_scenario_delivery_artifact_candidate_type", table_name="scenario_delivery_artifacts")
    for name in reversed(("scenario_id", "artifact_type", "snapshot_hash", "content_sha256", "status")):
        op.drop_index(f"ix_scenario_delivery_artifacts_{name}", table_name="scenario_delivery_artifacts")
    op.drop_table("scenario_delivery_artifacts")
    op.drop_index("uq_scenario_uat_acceptance_accepted", table_name="scenario_uat_acceptances")
    for name in reversed(("scenario_id", "expert_attestation_id", "accepted_by", "snapshot_hash", "status", "expires_at")):
        op.drop_index(f"ix_scenario_uat_acceptances_{name}", table_name="scenario_uat_acceptances")
    op.drop_table("scenario_uat_acceptances")
    op.drop_index("uq_scenario_expert_attestation_active", table_name="scenario_expert_attestations")
    for name in reversed(("scenario_id", "credential_id", "signed_by", "snapshot_hash", "status", "expires_at")):
        op.drop_index(f"ix_scenario_expert_attestations_{name}", table_name="scenario_expert_attestations")
    op.drop_table("scenario_expert_attestations")
    op.drop_index("ix_legal_expert_credentials_status", table_name="legal_expert_credentials")
    op.drop_index("ix_legal_expert_credentials_jurisdiction", table_name="legal_expert_credentials")
    op.drop_index("ix_legal_expert_credentials_user_id", table_name="legal_expert_credentials")
    op.drop_table("legal_expert_credentials")
