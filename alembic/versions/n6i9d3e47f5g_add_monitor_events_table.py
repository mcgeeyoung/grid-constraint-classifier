"""Add monitor_events table for job execution tracking.

Revision ID: n6i9d3e47f5g
Revises: m5h8c2d36e4f
Create Date: 2026-02-28
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic
revision = "n6i9d3e47f5g"
down_revision = "m5h8c2d36e4f"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "monitor_events",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("job_name", sa.String(100), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("duration_sec", sa.Float),
        sa.Column("status", sa.String(20), server_default="running"),
        sa.Column("records_checked", sa.Integer, server_default="0"),
        sa.Column("records_updated", sa.Integer, server_default="0"),
        sa.Column("new_items_found", sa.Integer, server_default="0"),
        sa.Column("alerts_generated", sa.Integer, server_default="0"),
        sa.Column("error_message", sa.Text),
        sa.Column("summary", sa.String(1000)),
        sa.Column("details_json", sa.JSON),
    )
    op.create_index("ix_me_job_name", "monitor_events", ["job_name"])
    op.create_index("ix_me_status", "monitor_events", ["status"])
    op.create_index("ix_me_started_at", "monitor_events", ["started_at"])


def downgrade():
    op.drop_table("monitor_events")
