"""Add fail-closed mechanism-layer records.

Revision ID: 20260717_0003
Revises: 20260717_0002
Create Date: 2026-07-17
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260717_0003"
down_revision: Union[str, None] = "20260717_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "material_ledger_entries",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("scenario_id", sa.Integer(), nullable=False),
        sa.Column("block_id", sa.String(length=255), nullable=False),
        sa.Column("source_document", sa.String(length=512), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("state_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("extraction_task_id", sa.String(length=255), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("confirmation_note", sa.Text(), nullable=True),
        sa.Column("confirmed_by", sa.Integer(), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("state_history", sa.JSON(), nullable=False),
        sa.Column("revision", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["confirmed_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["scenario_id"], ["investigation_scenarios.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("scenario_id", "block_id", name="uq_material_ledger_scenario_block"),
    )
    op.create_index("ix_material_ledger_entries_scenario_id", "material_ledger_entries", ["scenario_id"])
    op.create_index("ix_material_ledger_entries_state", "material_ledger_entries", ["state"])

    op.create_table(
        "coverage_tasks",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("scenario_id", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=512), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("denominator_ref", sa.String(length=1024), nullable=False),
        sa.Column("denominator_snapshot_hash", sa.String(length=64), nullable=False),
        sa.Column("denominator_items", sa.JSON(), nullable=False),
        sa.Column("covered_items", sa.JSON(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["scenario_id"], ["investigation_scenarios.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_coverage_tasks_scenario_id", "coverage_tasks", ["scenario_id"])
    op.create_index("ix_coverage_tasks_state", "coverage_tasks", ["state"])

    op.create_table(
        "fact_records",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("scenario_id", sa.Integer(), nullable=False),
        sa.Column("subject", sa.String(length=512), nullable=False),
        sa.Column("attribute", sa.String(length=512), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("fact_time", sa.String(length=128), nullable=False),
        sa.Column("block_id", sa.String(length=255), nullable=False),
        sa.Column("fact_pack_version", sa.String(length=64), nullable=False),
        sa.Column("source_document", sa.String(length=512), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("confirmation_note", sa.Text(), nullable=True),
        sa.Column("business_confirmed_by", sa.Integer(), nullable=True),
        sa.Column("business_confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["business_confirmed_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["scenario_id"], ["investigation_scenarios.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_fact_records_scenario_id", "fact_records", ["scenario_id"])
    op.create_index("ix_fact_records_status", "fact_records", ["status"])

    op.create_table(
        "claim_compilations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("scenario_id", sa.Integer(), nullable=False),
        sa.Column("compiler_version", sa.String(length=16), nullable=False),
        sa.Column("input_hash", sa.String(length=64), nullable=False),
        sa.Column("output_hash", sa.String(length=64), nullable=False),
        sa.Column("input_snapshot", sa.JSON(), nullable=False),
        sa.Column("denominator_count", sa.Integer(), nullable=False),
        sa.Column("ready_count", sa.Integer(), nullable=False),
        sa.Column("refused_count", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["scenario_id"], ["investigation_scenarios.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_claim_compilations_scenario_id", "claim_compilations", ["scenario_id"])
    op.create_index("ix_claim_compilations_input_hash", "claim_compilations", ["input_hash"])
    op.create_index("ix_claim_compilations_output_hash", "claim_compilations", ["output_hash"])

    op.create_table(
        "claim_records",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("compilation_id", sa.String(length=36), nullable=False),
        sa.Column("scenario_id", sa.Integer(), nullable=False),
        sa.Column("checklist_code", sa.String(length=128), nullable=False),
        sa.Column("statement", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("fact_refs", sa.JSON(), nullable=False),
        sa.Column("evidence_refs", sa.JSON(), nullable=False),
        sa.Column("reason_codes", sa.JSON(), nullable=False),
        sa.Column("confirmed_by", sa.Integer(), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confirmation_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["compilation_id"], ["claim_compilations.id"]),
        sa.ForeignKeyConstraint(["confirmed_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["scenario_id"], ["investigation_scenarios.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("compilation_id", "checklist_code", name="uq_claim_compilation_code"),
    )
    op.create_index("ix_claim_records_compilation_id", "claim_records", ["compilation_id"])
    op.create_index("ix_claim_records_scenario_id", "claim_records", ["scenario_id"])
    op.create_index("ix_claim_records_status", "claim_records", ["status"])

    op.create_table(
        "coverage_proofs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("scenario_id", sa.Integer(), nullable=False),
        sa.Column("compilation_id", sa.String(length=36), nullable=False),
        sa.Column("denominator_ref", sa.String(length=1024), nullable=False),
        sa.Column("denominator_hash", sa.String(length=64), nullable=False),
        sa.Column("denominator_count", sa.Integer(), nullable=False),
        sa.Column("covered_count", sa.Integer(), nullable=False),
        sa.Column("uncovered_count", sa.Integer(), nullable=False),
        sa.Column("unanswerable_count", sa.Integer(), nullable=False),
        sa.Column("proof", sa.JSON(), nullable=False),
        sa.Column("proof_hash", sa.String(length=64), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["compilation_id"], ["claim_compilations.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["scenario_id"], ["investigation_scenarios.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_coverage_proofs_scenario_id", "coverage_proofs", ["scenario_id"])
    op.create_index("ix_coverage_proofs_compilation_id", "coverage_proofs", ["compilation_id"])
    op.create_index("ix_coverage_proofs_proof_hash", "coverage_proofs", ["proof_hash"])


def downgrade() -> None:
    op.drop_index("ix_coverage_proofs_proof_hash", table_name="coverage_proofs")
    op.drop_index("ix_coverage_proofs_compilation_id", table_name="coverage_proofs")
    op.drop_index("ix_coverage_proofs_scenario_id", table_name="coverage_proofs")
    op.drop_table("coverage_proofs")
    op.drop_index("ix_claim_records_status", table_name="claim_records")
    op.drop_index("ix_claim_records_scenario_id", table_name="claim_records")
    op.drop_index("ix_claim_records_compilation_id", table_name="claim_records")
    op.drop_table("claim_records")
    op.drop_index("ix_claim_compilations_output_hash", table_name="claim_compilations")
    op.drop_index("ix_claim_compilations_input_hash", table_name="claim_compilations")
    op.drop_index("ix_claim_compilations_scenario_id", table_name="claim_compilations")
    op.drop_table("claim_compilations")
    op.drop_index("ix_fact_records_status", table_name="fact_records")
    op.drop_index("ix_fact_records_scenario_id", table_name="fact_records")
    op.drop_table("fact_records")
    op.drop_index("ix_coverage_tasks_state", table_name="coverage_tasks")
    op.drop_index("ix_coverage_tasks_scenario_id", table_name="coverage_tasks")
    op.drop_table("coverage_tasks")
    op.drop_index("ix_material_ledger_entries_state", table_name="material_ledger_entries")
    op.drop_index("ix_material_ledger_entries_scenario_id", table_name="material_ledger_entries")
    op.drop_table("material_ledger_entries")
