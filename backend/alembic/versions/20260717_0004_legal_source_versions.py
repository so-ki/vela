"""Add immutable legal source versions and structured change events.

Revision ID: 20260717_0004
Revises: 20260717_0003
Create Date: 2026-07-17
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260717_0004"
down_revision: Union[str, None] = "20260717_0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "legal_source_versions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("canonical_id", sa.String(length=512), nullable=False),
        sa.Column("citation_id", sa.String(length=1024), nullable=False),
        sa.Column("urn", sa.String(length=1024), nullable=True),
        sa.Column("source_authority", sa.String(length=512), nullable=False),
        sa.Column("official_domain", sa.String(length=255), nullable=False),
        sa.Column("official_source_basis", sa.Text(), nullable=False),
        sa.Column("source_url", sa.String(length=2048), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("etag", sa.String(length=1024), nullable=True),
        sa.Column("last_modified", sa.DateTime(timezone=True), nullable=True),
        sa.Column("raw_content", sa.Text(), nullable=False),
        sa.Column("normalized_content", sa.Text(), nullable=False),
        sa.Column("raw_hash", sa.String(length=64), nullable=False),
        sa.Column("normalized_hash", sa.String(length=64), nullable=False),
        sa.Column("parser_version", sa.String(length=64), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=True),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("relations", sa.JSON(), nullable=False),
        sa.Column("article_snapshots", sa.JSON(), nullable=False),
        sa.Column("previous_version_id", sa.String(length=36), nullable=True),
        sa.Column("decision_history", sa.JSON(), nullable=False),
        sa.Column("reviewed_by", sa.Integer(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("activated_by", sa.Integer(), nullable=True),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejected_by", sa.Integer(), nullable=True),
        sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision_note", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('candidate', 'reviewed', 'active', 'rejected')",
            name="ck_legal_source_version_status",
        ),
        sa.ForeignKeyConstraint(["activated_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["previous_version_id"], ["legal_source_versions.id"]),
        sa.ForeignKeyConstraint(["rejected_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["reviewed_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "canonical_id",
            "raw_hash",
            "normalized_hash",
            name="uq_legal_source_version_content",
        ),
    )
    op.create_index("ix_legal_source_versions_canonical_id", "legal_source_versions", ["canonical_id"])
    op.create_index("ix_legal_source_versions_citation_id", "legal_source_versions", ["citation_id"])
    op.create_index("ix_legal_source_versions_urn", "legal_source_versions", ["urn"])
    op.create_index("ix_legal_source_versions_raw_hash", "legal_source_versions", ["raw_hash"])
    op.create_index(
        "ix_legal_source_versions_normalized_hash", "legal_source_versions", ["normalized_hash"]
    )
    op.create_index("ix_legal_source_versions_status", "legal_source_versions", ["status"])
    op.create_index(
        "ix_legal_source_versions_previous_version_id",
        "legal_source_versions",
        ["previous_version_id"],
    )

    op.create_table(
        "legal_change_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("source_version_id", sa.String(length=36), nullable=False),
        sa.Column("previous_version_id", sa.String(length=36), nullable=True),
        sa.Column("canonical_id", sa.String(length=512), nullable=False),
        sa.Column("change_type", sa.String(length=32), nullable=False),
        sa.Column("article_diff", sa.JSON(), nullable=False),
        sa.Column("relation_diff", sa.JSON(), nullable=False),
        sa.Column("raw_hash_before", sa.String(length=64), nullable=True),
        sa.Column("raw_hash_after", sa.String(length=64), nullable=False),
        sa.Column("normalized_hash_before", sa.String(length=64), nullable=True),
        sa.Column("normalized_hash_after", sa.String(length=64), nullable=False),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "change_type IN ('initial', 'content_changed', 'format_only')",
            name="ck_legal_change_event_type",
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["previous_version_id"], ["legal_source_versions.id"]),
        sa.ForeignKeyConstraint(["source_version_id"], ["legal_source_versions.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_version_id", name="uq_legal_change_event_source_version"),
    )
    op.create_index(
        "ix_legal_change_events_source_version_id", "legal_change_events", ["source_version_id"]
    )
    op.create_index(
        "ix_legal_change_events_previous_version_id", "legal_change_events", ["previous_version_id"]
    )
    op.create_index("ix_legal_change_events_canonical_id", "legal_change_events", ["canonical_id"])
    op.create_index("ix_legal_change_events_change_type", "legal_change_events", ["change_type"])


def downgrade() -> None:
    op.drop_index("ix_legal_change_events_change_type", table_name="legal_change_events")
    op.drop_index("ix_legal_change_events_canonical_id", table_name="legal_change_events")
    op.drop_index("ix_legal_change_events_previous_version_id", table_name="legal_change_events")
    op.drop_index("ix_legal_change_events_source_version_id", table_name="legal_change_events")
    op.drop_table("legal_change_events")
    op.drop_index("ix_legal_source_versions_previous_version_id", table_name="legal_source_versions")
    op.drop_index("ix_legal_source_versions_status", table_name="legal_source_versions")
    op.drop_index("ix_legal_source_versions_normalized_hash", table_name="legal_source_versions")
    op.drop_index("ix_legal_source_versions_raw_hash", table_name="legal_source_versions")
    op.drop_index("ix_legal_source_versions_urn", table_name="legal_source_versions")
    op.drop_index("ix_legal_source_versions_citation_id", table_name="legal_source_versions")
    op.drop_index("ix_legal_source_versions_canonical_id", table_name="legal_source_versions")
    op.drop_table("legal_source_versions")
