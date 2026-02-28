"""Add interconnection_queue table for tracking DER/generation
interconnection requests from LBNL, utilities, and ISO portals.

Revision ID: k3f6a0b14c2d
Revises: j2e5f9a03b1c
Create Date: 2026-02-28
"""

from alembic import op
import sqlalchemy as sa
from geoalchemy2 import Geometry

# revision identifiers, used by Alembic
revision = "k3f6a0b14c2d"
down_revision = "j2e5f9a03b1c"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "interconnection_queue",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("utility_id", sa.Integer, sa.ForeignKey("utilities.id")),
        sa.Column("iso_id", sa.Integer, sa.ForeignKey("isos.id")),
        # Queue identification
        sa.Column("queue_id", sa.String(100), nullable=False),
        sa.Column("project_name", sa.String(500)),
        # Location
        sa.Column("state", sa.String(2)),
        sa.Column("county", sa.String(100)),
        sa.Column("point_of_interconnection", sa.String(300)),
        sa.Column("geom", Geometry("POINT", srid=4326)),
        sa.Column("latitude", sa.Float),
        sa.Column("longitude", sa.Float),
        # Project details
        sa.Column("generation_type", sa.String(50)),
        sa.Column("fuel_type", sa.String(50)),
        sa.Column("capacity_mw", sa.Float),
        sa.Column("capacity_mw_storage", sa.Float),
        # Status and dates
        sa.Column("queue_status", sa.String(50)),
        sa.Column("date_entered", sa.Date),
        sa.Column("date_completed", sa.Date),
        sa.Column("date_withdrawn", sa.Date),
        sa.Column("proposed_online_date", sa.Date),
        # Study phase
        sa.Column("study_phase", sa.String(50)),
        # Interconnection details
        sa.Column("voltage_kv", sa.Float),
        sa.Column("substation_name", sa.String(300)),
        # Data source
        sa.Column("data_source", sa.String(50), nullable=False),
        sa.Column("source_url", sa.String(1000)),
        sa.Column("raw_data", sa.JSON),
        # Provenance
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_iq_utility", "interconnection_queue", ["utility_id"])
    op.create_index("ix_iq_status", "interconnection_queue", ["queue_status"])
    op.create_index("ix_iq_type", "interconnection_queue", ["generation_type"])
    op.create_index("ix_iq_state", "interconnection_queue", ["state"])
    op.create_index(
        "ix_iq_geom", "interconnection_queue", ["geom"],
        postgresql_using="gist",
    )


def downgrade():
    op.drop_table("interconnection_queue")
