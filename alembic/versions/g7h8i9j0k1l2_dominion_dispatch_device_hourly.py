"""dominion dispatch schedule rows (device-hour)

Revision ID: g7h8i9j0k1l2
Revises: f1a2b3c4d5e6
Create Date: 2026-04-16

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "g7h8i9j0k1l2"
down_revision: Union[str, Sequence[str], None] = "f1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "dominion_dispatch_device_hourly",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("ingestion_run_id", sa.Integer(), nullable=False),
        sa.Column("device_id_external", sa.String(length=120), nullable=False),
        sa.Column("primary_pnode_id", sa.String(length=50), nullable=False),
        sa.Column("interval_start_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("raw_congestion", sa.Numeric(18, 6), nullable=True),
        sa.Column("resolved_congestion", sa.Numeric(18, 6), nullable=True),
        sa.Column("resolution_strategy", sa.String(length=40), nullable=False),
        sa.Column("source_pnode_id", sa.String(length=50), nullable=True),
        sa.Column("dispatch_signal", sa.Numeric(18, 6), nullable=True),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["ingestion_run_id"],
            ["dominion_da_ingestion_runs.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "ingestion_run_id",
            "device_id_external",
            "interval_start_utc",
            name="uq_dom_dispatch_run_dev_ts",
        ),
    )
    op.create_index(
        "ix_dom_dispatch_run_device",
        "dominion_dispatch_device_hourly",
        ["ingestion_run_id", "device_id_external"],
    )


def downgrade() -> None:
    op.drop_index("ix_dom_dispatch_run_device", table_name="dominion_dispatch_device_hourly")
    op.drop_table("dominion_dispatch_device_hourly")
