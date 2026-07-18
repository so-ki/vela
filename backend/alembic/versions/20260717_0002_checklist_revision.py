"""Add optimistic-lock revision to compliance checklist payloads.

Revision ID: 20260717_0002
Revises: 20260717_0001
Create Date: 2026-07-17
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260717_0002"
down_revision: Union[str, None] = "20260717_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # The server default backfills existing rows atomically and also makes a
    # rolling deployment safe if an older worker inserts during the migration.
    op.add_column(
        "compliance_checklists",
        sa.Column(
            "revision",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    with op.batch_alter_table("compliance_checklists") as batch_op:
        batch_op.drop_column("revision")
