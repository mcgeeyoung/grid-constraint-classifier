"""Add listed_capacity_kw to dominion_devices

Revision ID: k3l4m5n6o7p8
Revises: j2k3l4m5n6o7
Create Date: 2026-04-19
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "k3l4m5n6o7p8"
down_revision: Union[str, Sequence[str], None] = "j2k3l4m5n6o7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "dominion_devices",
        sa.Column("listed_capacity_kw", sa.Numeric(10, 2), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("dominion_devices", "listed_capacity_kw")
