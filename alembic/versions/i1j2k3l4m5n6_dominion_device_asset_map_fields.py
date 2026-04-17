"""dominion device: asset map location + primary pnode display name

Revision ID: i1j2k3l4m5n6
Revises: h8d0z0n3z0n3
Create Date: 2026-04-16

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "i1j2k3l4m5n6"
down_revision: Union[str, Sequence[str], None] = "h8d0z0n3z0n3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "dominion_devices",
        sa.Column("primary_pnode_name", sa.String(length=256), nullable=True),
    )
    op.add_column("dominion_devices", sa.Column("asset_lat", sa.Float(), nullable=True))
    op.add_column("dominion_devices", sa.Column("asset_lon", sa.Float(), nullable=True))
    op.add_column(
        "dominion_devices",
        sa.Column("asset_display_name", sa.String(length=200), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("dominion_devices", "asset_display_name")
    op.drop_column("dominion_devices", "asset_lon")
    op.drop_column("dominion_devices", "asset_lat")
    op.drop_column("dominion_devices", "primary_pnode_name")
