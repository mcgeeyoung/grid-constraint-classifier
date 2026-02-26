"""Link substations to zones and pnodes

Revision ID: c5e9f3a47b6d
Revises: b4d8e2f13a5c
Create Date: 2026-02-26
"""
from alembic import op
import sqlalchemy as sa

revision = "c5e9f3a47b6d"
down_revision = "b4d8e2f13a5c"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("substations", sa.Column("zone_id", sa.Integer(), nullable=True))
    op.add_column("substations", sa.Column("nearest_pnode_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_substations_zone_id", "substations", "zones",
        ["zone_id"], ["id"],
    )
    op.create_foreign_key(
        "fk_substations_nearest_pnode_id", "substations", "pnodes",
        ["nearest_pnode_id"], ["id"],
    )
    op.create_index("ix_substations_zone_id", "substations", ["zone_id"])


def downgrade() -> None:
    op.drop_index("ix_substations_zone_id", table_name="substations")
    op.drop_constraint("fk_substations_nearest_pnode_id", "substations", type_="foreignkey")
    op.drop_constraint("fk_substations_zone_id", "substations", type_="foreignkey")
    op.drop_column("substations", "nearest_pnode_id")
    op.drop_column("substations", "zone_id")
