"""Add data_coverage table for national coverage tracking.

Revision ID: m5h8c2d36e4f
Revises: l4g7b1c25d3e
Create Date: 2026-02-28
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic
revision = "m5h8c2d36e4f"
down_revision = "l4g7b1c25d3e"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "data_coverage",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("entity_type", sa.String(20), nullable=False),
        sa.Column("entity_id", sa.Integer),
        sa.Column("entity_name", sa.String(200), nullable=False),
        sa.Column("state", sa.String(2)),
        sa.Column("data_type", sa.String(50), nullable=False),
        sa.Column("has_data", sa.Boolean, server_default="false"),
        sa.Column("record_count", sa.Integer, server_default="0"),
        sa.Column("completeness_pct", sa.Float),
        sa.Column("latest_data_date", sa.DateTime(timezone=True)),
        sa.Column("last_checked_at", sa.DateTime(timezone=True)),
        sa.Column("last_updated_at", sa.DateTime(timezone=True)),
        sa.Column("data_source", sa.String(100)),
        sa.Column("quality_notes", sa.String(1000)),
        sa.Column("metadata_json", sa.JSON),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_dc_entity", "data_coverage", ["entity_type", "entity_id"])
    op.create_index("ix_dc_data_type", "data_coverage", ["data_type"])
    op.create_index("ix_dc_state", "data_coverage", ["state"])


def downgrade():
    op.drop_table("data_coverage")
