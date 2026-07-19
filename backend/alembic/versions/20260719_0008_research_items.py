"""Add independent ResearchItems and explicit business fact polarity.

Revision ID: 20260719_0008
Revises: 20260719_0007
Create Date: 2026-07-19
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260719_0008"
down_revision: Union[str, None] = "20260719_0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "fact_records",
        sa.Column(
            "assertion_polarity",
            sa.String(length=16),
            nullable=True,
            server_default=sa.text("'unspecified'"),
        ),
    )
    facts = sa.table(
        "fact_records",
        sa.column("assertion_polarity", sa.String(length=16)),
    )
    op.execute(
        facts.update()
        .where(facts.c.assertion_polarity.is_(None))
        .values(assertion_polarity="unspecified")
    )
    with op.batch_alter_table("fact_records") as batch_op:
        batch_op.alter_column(
            "assertion_polarity",
            existing_type=sa.String(length=16),
            nullable=False,
            server_default=None,
        )

    op.create_table(
        "research_items",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("compilation_id", sa.String(length=36), nullable=False),
        sa.Column("scenario_id", sa.Integer(), nullable=False),
        sa.Column("checklist_code", sa.String(length=128), nullable=False),
        sa.Column("denominator_order", sa.Integer(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("dimension", sa.String(length=64), nullable=False),
        sa.Column("scope_status", sa.String(length=32), nullable=False),
        sa.Column("screening_status", sa.String(length=32), nullable=False),
        sa.Column("disposition", sa.String(length=32), nullable=True),
        sa.Column("research_status", sa.String(length=32), nullable=False),
        sa.Column("missing_facts", sa.JSON(), nullable=False),
        sa.Column("reason_codes", sa.JSON(), nullable=False),
        sa.Column("negative_fact_refs", sa.JSON(), nullable=False),
        sa.Column("linked_claim_id", sa.String(length=36), nullable=True),
        sa.Column("compiler_version", sa.String(length=16), nullable=False),
        sa.Column("item_hash", sa.String(length=64), nullable=False),
        sa.Column("legal_confirmed_by", sa.Integer(), nullable=True),
        sa.Column("legal_confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("legal_confirmation_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["compilation_id"], ["claim_compilations.id"]),
        sa.ForeignKeyConstraint(["legal_confirmed_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["linked_claim_id"], ["claim_records.id"]),
        sa.ForeignKeyConstraint(["scenario_id"], ["investigation_scenarios.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "compilation_id",
            "checklist_code",
            name="uq_research_item_compilation_code",
        ),
    )
    op.create_index("ix_research_items_compilation_id", "research_items", ["compilation_id"])
    op.create_index("ix_research_items_scenario_id", "research_items", ["scenario_id"])
    op.create_index("ix_research_items_dimension", "research_items", ["dimension"])
    op.create_index("ix_research_items_scope_status", "research_items", ["scope_status"])
    op.create_index("ix_research_items_disposition", "research_items", ["disposition"])
    op.create_index("ix_research_items_research_status", "research_items", ["research_status"])
    op.create_index("ix_research_items_linked_claim_id", "research_items", ["linked_claim_id"])


def downgrade() -> None:
    bind = op.get_bind()
    research_count = bind.execute(sa.text("SELECT COUNT(*) FROM research_items")).scalar_one()
    non_default_fact_count = bind.execute(
        sa.text(
            "SELECT COUNT(*) FROM fact_records "
            "WHERE assertion_polarity <> 'unspecified' OR assertion_polarity IS NULL"
        )
    ).scalar_one()
    if research_count or non_default_fact_count:
        raise RuntimeError(
            "refusing to discard ResearchItems or explicit business fact polarity"
        )

    op.drop_index("ix_research_items_linked_claim_id", table_name="research_items")
    op.drop_index("ix_research_items_research_status", table_name="research_items")
    op.drop_index("ix_research_items_disposition", table_name="research_items")
    op.drop_index("ix_research_items_scope_status", table_name="research_items")
    op.drop_index("ix_research_items_dimension", table_name="research_items")
    op.drop_index("ix_research_items_scenario_id", table_name="research_items")
    op.drop_index("ix_research_items_compilation_id", table_name="research_items")
    op.drop_table("research_items")
    with op.batch_alter_table("fact_records") as batch_op:
        batch_op.drop_column("assertion_polarity")
