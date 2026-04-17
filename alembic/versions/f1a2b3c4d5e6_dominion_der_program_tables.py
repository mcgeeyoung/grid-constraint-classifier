"""dominion DER program: DA ingestion + hourly node congestion + devices

Revision ID: f1a2b3c4d5e6
Revises: b4d8e2f13a5c
Create Date: 2026-04-16

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f1a2b3c4d5e6"
down_revision: Union[str, Sequence[str], None] = "b4d8e2f13a5c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "dominion_da_ingestion_runs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("idempotency_key", sa.String(length=220), nullable=False),
        sa.Column("operating_date", sa.Date(), nullable=False),
        sa.Column("zone_code", sa.String(length=20), nullable=False),
        sa.Column("lmp_type", sa.String(length=20), nullable=False),
        sa.Column("data_source", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("retrieved_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("request_started_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("request_completed_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("row_count", sa.Integer(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("query_date_range", sa.String(length=500), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key", name="uq_dominion_da_runs_idem"),
    )
    op.create_index(
        "ix_dominion_da_runs_operating_zone_lmp",
        "dominion_da_ingestion_runs",
        ["operating_date", "zone_code", "lmp_type"],
    )

    op.create_table(
        "dominion_da_node_hourly",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("ingestion_run_id", sa.Integer(), nullable=False),
        sa.Column("operating_date", sa.Date(), nullable=False),
        sa.Column("zone_code", sa.String(length=20), nullable=False),
        sa.Column("lmp_type", sa.String(length=20), nullable=False),
        sa.Column("interval_start_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("pnode_id_external", sa.String(length=50), nullable=False),
        sa.Column("pnode_name", sa.String(length=256), nullable=True),
        sa.Column("congestion_price_da", sa.Numeric(18, 6), nullable=True),
        sa.Column("total_lmp_da", sa.Numeric(18, 6), nullable=True),
        sa.Column("marginal_loss_price_da", sa.Numeric(18, 6), nullable=True),
        sa.Column("system_energy_price_da", sa.Numeric(18, 6), nullable=True),
        sa.ForeignKeyConstraint(
            ["ingestion_run_id"],
            ["dominion_da_ingestion_runs.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "ingestion_run_id",
            "pnode_id_external",
            "interval_start_utc",
            name="uq_dominion_da_node_hourly_run_pnode_ts",
        ),
    )
    op.create_index(
        "ix_dominion_da_node_hourly_operating_pnode",
        "dominion_da_node_hourly",
        ["operating_date", "pnode_id_external"],
    )
    op.create_index(
        "ix_dominion_da_node_hourly_run",
        "dominion_da_node_hourly",
        ["ingestion_run_id"],
    )

    op.create_table(
        "dominion_devices",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("device_id_external", sa.String(length=120), nullable=False),
        sa.Column("primary_pnode_id", sa.String(length=50), nullable=False),
        sa.Column("neighbor_pnode_ids", sa.JSON(), nullable=True),
        sa.Column("piecewise_curve", sa.JSON(), nullable=True),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("device_id_external", name="uq_dominion_devices_ext_id"),
    )


def downgrade() -> None:
    op.drop_table("dominion_devices")
    op.drop_index("ix_dominion_da_node_hourly_run", table_name="dominion_da_node_hourly")
    op.drop_index("ix_dominion_da_node_hourly_operating_pnode", table_name="dominion_da_node_hourly")
    op.drop_table("dominion_da_node_hourly")
    op.drop_index("ix_dominion_da_runs_operating_zone_lmp", table_name="dominion_da_ingestion_runs")
    op.drop_table("dominion_da_ingestion_runs")
