"""add transmission_lines and substations tables

Revision ID: a3f7c1d92e4b
Revises: edba30b2006c
Create Date: 2026-02-25 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "a3f7c1d92e4b"
down_revision: Union[str, None] = "edba30b2006c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "transmission_lines",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("iso_id", sa.Integer(), sa.ForeignKey("isos.id"), nullable=False),
        sa.Column("voltage_kv", sa.Integer(), nullable=True),
        sa.Column("owner", sa.String(200), nullable=True),
        sa.Column("sub_1", sa.String(200), nullable=True),
        sa.Column("sub_2", sa.String(200), nullable=True),
        sa.Column("shape_length", sa.Float(), nullable=True),
        sa.Column("geometry_json", sa.JSON(), nullable=True),
    )
    op.create_index(
        "ix_transmission_lines_iso_id",
        "transmission_lines",
        ["iso_id"],
    )

    op.create_table(
        "substations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("iso_id", sa.Integer(), sa.ForeignKey("isos.id"), nullable=False),
        sa.Column("substation_name", sa.String(200), nullable=False),
        sa.Column("bank_name", sa.String(200), nullable=True),
        sa.Column("division", sa.String(100), nullable=True),
        sa.Column("facility_rating_mw", sa.Float(), nullable=True),
        sa.Column("facility_loading_mw", sa.Float(), nullable=True),
        sa.Column("peak_loading_pct", sa.Float(), nullable=True),
        sa.Column("facility_type", sa.String(50), nullable=True),
        sa.Column("lat", sa.Float(), nullable=True),
        sa.Column("lon", sa.Float(), nullable=True),
        sa.UniqueConstraint(
            "iso_id", "substation_name", "bank_name",
            name="uq_substations",
        ),
    )
    op.create_index(
        "ix_substations_iso_id",
        "substations",
        ["iso_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_substations_iso_id", table_name="substations")
    op.drop_table("substations")
    op.drop_index("ix_transmission_lines_iso_id", table_name="transmission_lines")
    op.drop_table("transmission_lines")
