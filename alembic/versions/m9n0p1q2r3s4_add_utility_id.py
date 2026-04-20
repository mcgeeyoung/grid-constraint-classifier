"""Add utility_id to dominion_da tables for multi-tenant support

Revision ID: m9n0p1q2r3s4
Revises: k3l4m5n6o7p8
Create Date: 2026-04-19
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "m9n0p1q2r3s4"
down_revision: Union[str, Sequence[str], None] = "k3l4m5n6o7p8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add utility_id columns with server_default='dominion' so existing rows
    # are backfilled implicitly and future INSERTs that omit the column
    # (e.g. bulk_insert_mappings without utility_id) still populate it.
    op.add_column(
        "dominion_da_ingestion_runs",
        sa.Column(
            "utility_id",
            sa.Text(),
            nullable=False,
            server_default="dominion",
        ),
    )
    op.add_column(
        "dominion_da_node_hourly",
        sa.Column(
            "utility_id",
            sa.Text(),
            nullable=False,
            server_default="dominion",
        ),
    )

    op.create_index(
        "ix_dominion_da_ingestion_runs_utility_opdate",
        "dominion_da_ingestion_runs",
        ["utility_id", "operating_date"],
    )
    op.create_index(
        "ix_dominion_da_node_hourly_utility_pnode",
        "dominion_da_node_hourly",
        ["utility_id", "pnode_id_external"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_dominion_da_node_hourly_utility_pnode",
        table_name="dominion_da_node_hourly",
    )
    op.drop_index(
        "ix_dominion_da_ingestion_runs_utility_opdate",
        table_name="dominion_da_ingestion_runs",
    )
    op.drop_column("dominion_da_node_hourly", "utility_id")
    op.drop_column("dominion_da_ingestion_runs", "utility_id")
