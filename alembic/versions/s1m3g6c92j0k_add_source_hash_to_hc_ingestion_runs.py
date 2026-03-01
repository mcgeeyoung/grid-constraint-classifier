"""add source_hash to hc_ingestion_runs

Revision ID: s1m3g6c92j0k
Revises: r0m3g5b81i9j
Create Date: 2026-03-01
"""

from alembic import op
import sqlalchemy as sa


revision = "s1m3g6c92j0k"
down_revision = "2c12a7b1e62d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "hc_ingestion_runs",
        sa.Column("source_hash", sa.String(64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("hc_ingestion_runs", "source_hash")
