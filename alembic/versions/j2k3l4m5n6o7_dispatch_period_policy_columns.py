"""dominion dispatch: stressed / extreme period columns

Revision ID: j2k3l4m5n6o7
Revises: i1j2k3l4m5n6
Create Date: 2026-04-16

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "j2k3l4m5n6o7"
down_revision: Union[str, Sequence[str], None] = "i1j2k3l4m5n6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "dominion_dispatch_device_hourly",
        sa.Column("extreme_abs_threshold_usd", sa.Numeric(18, 6), nullable=True),
    )
    op.add_column(
        "dominion_dispatch_device_hourly",
        sa.Column("period_tier", sa.String(length=24), nullable=True),
    )
    op.add_column(
        "dominion_dispatch_device_hourly",
        sa.Column("dispatch_mandatory", sa.Boolean(), nullable=True),
    )
    op.add_column(
        "dominion_dispatch_device_hourly",
        sa.Column("dispatch_signal_program", sa.Numeric(18, 6), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("dominion_dispatch_device_hourly", "dispatch_signal_program")
    op.drop_column("dominion_dispatch_device_hourly", "dispatch_mandatory")
    op.drop_column("dominion_dispatch_device_hourly", "period_tier")
    op.drop_column("dominion_dispatch_device_hourly", "extreme_abs_threshold_usd")
