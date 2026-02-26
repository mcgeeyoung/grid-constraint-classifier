"""Add retrospective valuation fields to der_valuations

Revision ID: e7a1b5c69d8f
Revises: d6f0a4b58c7e
Create Date: 2026-02-26
"""
from alembic import op
import sqlalchemy as sa

revision = "e7a1b5c69d8f"
down_revision = "d6f0a4b58c7e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("der_valuations", sa.Column("actual_savings_mwh", sa.Float(), nullable=True))
    op.add_column("der_valuations", sa.Column("actual_constraint_relief_value", sa.Float(), nullable=True))
    op.add_column("der_valuations", sa.Column("actual_zone_congestion_value", sa.Float(), nullable=True))
    op.add_column("der_valuations", sa.Column("actual_substation_value", sa.Float(), nullable=True))
    op.add_column("der_valuations", sa.Column("actual_feeder_value", sa.Float(), nullable=True))
    op.add_column("der_valuations", sa.Column("retrospective_start", sa.DateTime(timezone=True), nullable=True))
    op.add_column("der_valuations", sa.Column("retrospective_end", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("der_valuations", "retrospective_end")
    op.drop_column("der_valuations", "retrospective_start")
    op.drop_column("der_valuations", "actual_feeder_value")
    op.drop_column("der_valuations", "actual_substation_value")
    op.drop_column("der_valuations", "actual_zone_congestion_value")
    op.drop_column("der_valuations", "actual_constraint_relief_value")
    op.drop_column("der_valuations", "actual_savings_mwh")
