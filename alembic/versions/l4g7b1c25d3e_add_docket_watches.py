"""Add docket_watches table for PUC docket monitoring.

Revision ID: l4g7b1c25d3e
Revises: k3f6a0b14c2d
Create Date: 2026-02-28
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic
revision = "l4g7b1c25d3e"
down_revision = "k3f6a0b14c2d"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "docket_watches",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("state", sa.String(2), nullable=False),
        sa.Column("docket_number", sa.String(100), nullable=False),
        sa.Column("title", sa.String(500)),
        sa.Column("utility_name", sa.String(200)),
        sa.Column("filing_type", sa.String(50)),
        sa.Column("priority", sa.Integer, server_default="2"),
        sa.Column("is_active", sa.Boolean, server_default="true"),
        sa.Column("last_checked_at", sa.DateTime(timezone=True)),
        sa.Column("last_filing_date", sa.DateTime(timezone=True)),
        sa.Column("filings_count", sa.Integer, server_default="0"),
        sa.Column("notes", sa.String(1000)),
        sa.Column("metadata_json", sa.JSON),
        sa.Column("regulator_id", sa.Integer, sa.ForeignKey("regulators.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_dw_state", "docket_watches", ["state"])
    op.create_index("ix_dw_active", "docket_watches", ["is_active"])


def downgrade():
    op.drop_table("docket_watches")
