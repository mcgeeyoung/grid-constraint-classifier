"""Widen zone_code column from varchar(20) to varchar(50)

Revision ID: b4d8e2f13a5c
Revises: a3f7c1d92e4b
Create Date: 2026-02-25
"""
from alembic import op
import sqlalchemy as sa

revision = "b4d8e2f13a5c"
down_revision = "a3f7c1d92e4b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("zones", "zone_code",
                     existing_type=sa.String(20),
                     type_=sa.String(50),
                     existing_nullable=False)


def downgrade() -> None:
    op.alter_column("zones", "zone_code",
                     existing_type=sa.String(50),
                     type_=sa.String(20),
                     existing_nullable=False)
