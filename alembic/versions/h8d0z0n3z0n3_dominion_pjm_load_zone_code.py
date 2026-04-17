"""dominion: PJM load zone (settlement) code on devices and dispatch rows

Revision ID: h8d0z0n3z0n3
Revises: g7h8i9j0k1l2
Create Date: 2026-04-16

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "h8d0z0n3z0n3"
down_revision: Union[str, Sequence[str], None] = "g7h8i9j0k1l2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "dominion_devices",
        sa.Column(
            "pjm_load_zone_code",
            sa.String(length=20),
            nullable=False,
            server_default="DOM",
        ),
    )
    op.add_column(
        "dominion_dispatch_device_hourly",
        sa.Column(
            "pjm_load_zone_code",
            sa.String(length=20),
            nullable=False,
            server_default="DOM",
        ),
    )
    op.create_index(
        "ix_dominion_devices_load_zone",
        "dominion_devices",
        ["pjm_load_zone_code"],
    )
    op.alter_column("dominion_devices", "pjm_load_zone_code", server_default=None)
    op.alter_column(
        "dominion_dispatch_device_hourly", "pjm_load_zone_code", server_default=None
    )


def downgrade() -> None:
    op.drop_index("ix_dominion_devices_load_zone", table_name="dominion_devices")
    op.drop_column("dominion_dispatch_device_hourly", "pjm_load_zone_code")
    op.drop_column("dominion_devices", "pjm_load_zone_code")
