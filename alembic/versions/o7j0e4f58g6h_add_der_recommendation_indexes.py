"""Add missing indexes on der_recommendations FK columns.

Revision ID: o7j0e4f58g6h
Revises: n6i9d3e47f5g
Create Date: 2026-02-28
"""

from alembic import op

# revision identifiers, used by Alembic
revision = "o7j0e4f58g6h"
down_revision = "n6i9d3e47f5g"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index("ix_der_recs_pipeline_run_id", "der_recommendations", ["pipeline_run_id"])
    op.create_index("ix_der_recs_zone_id", "der_recommendations", ["zone_id"])


def downgrade():
    op.drop_index("ix_der_recs_zone_id", table_name="der_recommendations")
    op.drop_index("ix_der_recs_pipeline_run_id", table_name="der_recommendations")
