"""Persist the exact delivery release reader identity.

Revision ID: 20260719_0007
Revises: 20260718_0006
Create Date: 2026-07-19
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260719_0007"
down_revision: Union[str, None] = "20260718_0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # The default exists only while old rows are backfilled. It is deliberately
    # removed before upgrade returns so every writer must persist reader.version.
    op.add_column(
        "scenario_delivery_releases",
        sa.Column(
            "schema_version",
            sa.String(length=16),
            nullable=True,
            server_default=sa.text("'1.1'"),
        ),
    )
    releases = sa.table(
        "scenario_delivery_releases",
        sa.column("schema_version", sa.String(length=16)),
    )
    op.execute(
        releases.update()
        .where(releases.c.schema_version.is_(None))
        .values(schema_version="1.1")
    )
    with op.batch_alter_table("scenario_delivery_releases") as batch_op:
        batch_op.alter_column(
            "schema_version",
            existing_type=sa.String(length=16),
            nullable=False,
            server_default=None,
        )


def downgrade() -> None:
    bind = op.get_bind()
    unsupported = bind.execute(
        sa.text(
            "SELECT COUNT(*) FROM scenario_delivery_releases "
            "WHERE schema_version <> '1.1' OR schema_version IS NULL"
        )
    ).scalar_one()
    if unsupported:
        raise RuntimeError(
            "refusing to drop delivery release schema identity for non-1.1 rows"
        )
    with op.batch_alter_table("scenario_delivery_releases") as batch_op:
        batch_op.drop_column("schema_version")
