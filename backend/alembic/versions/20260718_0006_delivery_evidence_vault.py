"""Add immutable delivery evidence objects and deployment receipts.

Revision ID: 20260718_0006
Revises: 20260718_0005
Create Date: 2026-07-18
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260718_0006"
down_revision: Union[str, None] = "20260718_0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "delivery_evidence_objects",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("scenario_id", sa.Integer(), nullable=True),
        sa.Column("evidence_kind", sa.String(length=64), nullable=False),
        sa.Column("filename", sa.String(length=512), nullable=False),
        sa.Column("media_type", sa.String(length=255), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("content_length", sa.Integer(), nullable=False),
        sa.Column("content", sa.LargeBinary(), nullable=False),
        sa.Column("source_url", sa.String(length=2048), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("uploaded_by", sa.Integer(), nullable=False),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_by", sa.Integer(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revocation_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
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
        sa.CheckConstraint(
            "status IN ('available','revoked')",
            name="ck_delivery_evidence_object_status",
        ),
        sa.ForeignKeyConstraint(["revoked_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["scenario_id"], ["investigation_scenarios.id"]),
        sa.ForeignKeyConstraint(["uploaded_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "evidence_kind",
            "content_sha256",
            name="uq_delivery_evidence_kind_content_sha256",
        ),
    )
    for column in (
        "scenario_id",
        "evidence_kind",
        "content_sha256",
        "status",
        "uploaded_by",
        "expires_at",
    ):
        op.create_index(
            f"ix_delivery_evidence_objects_{column}",
            "delivery_evidence_objects",
            [column],
        )
    op.add_column(
        "deployment_evidence",
        sa.Column("artifact_receipt_hash", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "deployment_evidence",
        sa.Column("security_evidence_sha256", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("deployment_evidence", "security_evidence_sha256")
    op.drop_column("deployment_evidence", "artifact_receipt_hash")
    op.drop_table("delivery_evidence_objects")
