"""Create the complete Vela application schema.

Revision ID: 20260717_0001
Revises:
Create Date: 2026-07-17
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260717_0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("full_name", sa.String(length=128), nullable=False),
        sa.Column("hashed_password", sa.String(length=255), nullable=True),
        sa.Column("organization", sa.String(length=255), nullable=True),
        sa.Column(
            "role",
            sa.String(length=32),
            server_default=sa.text("'business'"),
            nullable=False,
        ),
        sa.Column("auth_provider", sa.String(length=32), nullable=False),
        sa.Column("external_subject", sa.String(length=255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("disclaimer_accepted", sa.Boolean(), nullable=False),
        sa.Column("disclaimer_accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index(
        "ix_users_external_subject", "users", ["external_subject"], unique=False
    )

    op.create_table(
        "investigation_scenarios",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("project_name", sa.String(length=255), nullable=False),
        sa.Column("country", sa.String(length=64), nullable=False),
        sa.Column("rules_pack_id", sa.String(length=64), nullable=True),
        sa.Column("scenario_scope", sa.JSON(), nullable=True),
        sa.Column("scope_snapshot_hash", sa.String(length=64), nullable=True),
        sa.Column("active_generation_attempt_id", sa.String(length=36), nullable=True),
        sa.Column("is_demo", sa.Boolean(), nullable=False),
        sa.Column("state", sa.String(length=64), nullable=False),
        sa.Column("city", sa.String(length=64), nullable=False),
        sa.Column("industry", sa.String(length=64), nullable=False),
        sa.Column("action_type", sa.String(length=64), nullable=False),
        sa.Column("investment_structure", sa.Text(), nullable=True),
        sa.Column("investment_destination", sa.String(length=512), nullable=True),
        sa.Column("project_content_scale", sa.String(length=512), nullable=True),
        sa.Column("funding_source", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("known_risks", sa.Text(), nullable=True),
        sa.Column("employee_count", sa.Integer(), nullable=True),
        sa.Column("capacity_notes", sa.String(length=512), nullable=True),
        sa.Column("facility_notes", sa.String(length=512), nullable=True),
        sa.Column("compliance_dimensions", sa.JSON(), nullable=False),
        sa.Column("board_date", sa.Date(), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("production_date", sa.Date(), nullable=True),
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("business_archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("legal_deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_investigation_scenarios_active_generation_attempt_id",
        "investigation_scenarios",
        ["active_generation_attempt_id"],
        unique=False,
    )
    op.create_index(
        "ix_investigation_scenarios_scope_snapshot_hash",
        "investigation_scenarios",
        ["scope_snapshot_hash"],
        unique=False,
    )
    op.create_index(
        "ix_investigation_scenarios_user_id",
        "investigation_scenarios",
        ["user_id"],
        unique=False,
    )

    op.create_table(
        "compliance_checklists",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("scenario_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("version", sa.String(length=16), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("total_items", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["scenario_id"], ["investigation_scenarios.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_compliance_checklists_scenario_id",
        "compliance_checklists",
        ["scenario_id"],
        unique=True,
    )

    op.create_table(
        "scenario_generation_inputs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("scenario_id", sa.Integer(), nullable=False),
        sa.Column("input_hash", sa.String(length=64), nullable=False),
        sa.Column("schema_version", sa.String(length=16), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["scenario_id"], ["investigation_scenarios.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_scenario_generation_inputs_input_hash",
        "scenario_generation_inputs",
        ["input_hash"],
        unique=False,
    )
    op.create_index(
        "ix_scenario_generation_inputs_scenario_id",
        "scenario_generation_inputs",
        ["scenario_id"],
        unique=False,
    )

    op.create_table(
        "scenario_generation_attempts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("scenario_id", sa.Integer(), nullable=False),
        sa.Column("snapshot_hash", sa.String(length=64), nullable=False),
        sa.Column("config_hash", sa.String(length=64), nullable=False),
        sa.Column("generation_input_id", sa.String(length=36), nullable=False),
        sa.Column("generation_input_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("lease_owner", sa.String(length=128), nullable=False),
        sa.Column("lease_token", sa.String(length=64), nullable=False),
        sa.Column("lease_acquired_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(
            ["generation_input_id"], ["scenario_generation_inputs.id"]
        ),
        sa.ForeignKeyConstraint(["scenario_id"], ["investigation_scenarios.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "scenario_id", "sequence", name="uq_generation_attempt_sequence"
        ),
    )
    op.create_index(
        "ix_scenario_generation_attempts_config_hash",
        "scenario_generation_attempts",
        ["config_hash"],
        unique=False,
    )
    op.create_index(
        "ix_scenario_generation_attempts_generation_input_hash",
        "scenario_generation_attempts",
        ["generation_input_hash"],
        unique=False,
    )
    op.create_index(
        "ix_scenario_generation_attempts_generation_input_id",
        "scenario_generation_attempts",
        ["generation_input_id"],
        unique=False,
    )
    op.create_index(
        "ix_scenario_generation_attempts_lease_expires_at",
        "scenario_generation_attempts",
        ["lease_expires_at"],
        unique=False,
    )
    op.create_index(
        "ix_scenario_generation_attempts_lease_token",
        "scenario_generation_attempts",
        ["lease_token"],
        unique=True,
    )
    op.create_index(
        "ix_scenario_generation_attempts_scenario_id",
        "scenario_generation_attempts",
        ["scenario_id"],
        unique=False,
    )
    op.create_index(
        "ix_scenario_generation_attempts_snapshot_hash",
        "scenario_generation_attempts",
        ["snapshot_hash"],
        unique=False,
    )
    op.create_index(
        "ix_scenario_generation_attempts_status",
        "scenario_generation_attempts",
        ["status"],
        unique=False,
    )

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("resource_type", sa.String(length=64), nullable=True),
        sa.Column("resource_id", sa.String(length=64), nullable=True),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("ip_address", sa.String(length=45), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_audit_logs_user_id", "audit_logs", ["user_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_audit_logs_user_id", table_name="audit_logs")
    op.drop_table("audit_logs")

    op.drop_index(
        "ix_scenario_generation_attempts_status",
        table_name="scenario_generation_attempts",
    )
    op.drop_index(
        "ix_scenario_generation_attempts_snapshot_hash",
        table_name="scenario_generation_attempts",
    )
    op.drop_index(
        "ix_scenario_generation_attempts_scenario_id",
        table_name="scenario_generation_attempts",
    )
    op.drop_index(
        "ix_scenario_generation_attempts_lease_token",
        table_name="scenario_generation_attempts",
    )
    op.drop_index(
        "ix_scenario_generation_attempts_lease_expires_at",
        table_name="scenario_generation_attempts",
    )
    op.drop_index(
        "ix_scenario_generation_attempts_generation_input_id",
        table_name="scenario_generation_attempts",
    )
    op.drop_index(
        "ix_scenario_generation_attempts_generation_input_hash",
        table_name="scenario_generation_attempts",
    )
    op.drop_index(
        "ix_scenario_generation_attempts_config_hash",
        table_name="scenario_generation_attempts",
    )
    op.drop_table("scenario_generation_attempts")

    op.drop_index(
        "ix_scenario_generation_inputs_scenario_id",
        table_name="scenario_generation_inputs",
    )
    op.drop_index(
        "ix_scenario_generation_inputs_input_hash",
        table_name="scenario_generation_inputs",
    )
    op.drop_table("scenario_generation_inputs")

    op.drop_index(
        "ix_compliance_checklists_scenario_id", table_name="compliance_checklists"
    )
    op.drop_table("compliance_checklists")

    op.drop_index(
        "ix_investigation_scenarios_user_id", table_name="investigation_scenarios"
    )
    op.drop_index(
        "ix_investigation_scenarios_scope_snapshot_hash",
        table_name="investigation_scenarios",
    )
    op.drop_index(
        "ix_investigation_scenarios_active_generation_attempt_id",
        table_name="investigation_scenarios",
    )
    op.drop_table("investigation_scenarios")

    op.drop_index("ix_users_external_subject", table_name="users")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
