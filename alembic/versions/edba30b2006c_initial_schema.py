"""initial schema

Revision ID: edba30b2006c
Revises:
Create Date: 2026-02-22 18:11:30.609472

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'edba30b2006c'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create all tables for the grid constraint classifier."""

    # ISOs
    op.create_table(
        "isos",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("iso_code", sa.String(10), unique=True, nullable=False),
        sa.Column("iso_name", sa.String(100), nullable=False),
        sa.Column("timezone", sa.String(50), nullable=False),
        sa.Column("has_decomposition", sa.Boolean, server_default="true"),
        sa.Column("has_node_pricing", sa.Boolean, server_default="true"),
        sa.Column("config_json", sa.JSON, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Zones
    op.create_table(
        "zones",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("iso_id", sa.Integer, sa.ForeignKey("isos.id"), nullable=False),
        sa.Column("zone_code", sa.String(20), nullable=False),
        sa.Column("zone_name", sa.String(100)),
        sa.Column("centroid_lat", sa.Float),
        sa.Column("centroid_lon", sa.Float),
        sa.Column("states", sa.JSON, nullable=True),
        sa.Column("boundary_geojson", sa.JSON, nullable=True),
        sa.UniqueConstraint("iso_id", "zone_code", name="uq_zones_iso_zone"),
    )

    # Zone LMPs
    op.create_table(
        "zone_lmps",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("iso_id", sa.Integer, sa.ForeignKey("isos.id"), nullable=False),
        sa.Column("zone_id", sa.Integer, sa.ForeignKey("zones.id"), nullable=False),
        sa.Column("timestamp_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lmp", sa.Float, nullable=False),
        sa.Column("energy", sa.Float),
        sa.Column("congestion", sa.Float),
        sa.Column("loss", sa.Float),
        sa.Column("hour_local", sa.SmallInteger, nullable=False),
        sa.Column("month", sa.SmallInteger, nullable=False),
        sa.UniqueConstraint("iso_id", "zone_id", "timestamp_utc", name="uq_zone_lmps"),
    )
    op.create_index("ix_zone_lmps_zone_ts", "zone_lmps", ["zone_id", "timestamp_utc"])
    op.create_index("ix_zone_lmps_iso_month", "zone_lmps", ["iso_id", "month"])

    # Pipeline runs
    op.create_table(
        "pipeline_runs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("iso_id", sa.Integer, sa.ForeignKey("isos.id"), nullable=False),
        sa.Column("year", sa.Integer, nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("status", sa.String(20), server_default="running"),
        sa.Column("zone_lmp_rows", sa.Integer),
        sa.Column("error_message", sa.Text),
    )

    # Zone classifications
    op.create_table(
        "zone_classifications",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("pipeline_run_id", sa.Integer, sa.ForeignKey("pipeline_runs.id")),
        sa.Column("zone_id", sa.Integer, sa.ForeignKey("zones.id")),
        sa.Column("classification", sa.String(20), nullable=False),
        sa.Column("transmission_score", sa.Float, nullable=False),
        sa.Column("generation_score", sa.Float, nullable=False),
        sa.Column("avg_abs_congestion", sa.Float),
        sa.Column("max_congestion", sa.Float),
        sa.Column("congested_hours_pct", sa.Float),
        sa.UniqueConstraint("pipeline_run_id", "zone_id", name="uq_zone_cls"),
    )

    # Pnodes
    op.create_table(
        "pnodes",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("iso_id", sa.Integer, sa.ForeignKey("isos.id")),
        sa.Column("zone_id", sa.Integer, sa.ForeignKey("zones.id"), nullable=True),
        sa.Column("node_id_external", sa.String(50), nullable=False),
        sa.Column("node_name", sa.String(100)),
        sa.Column("lat", sa.Float),
        sa.Column("lon", sa.Float),
        sa.UniqueConstraint("iso_id", "node_id_external", name="uq_pnodes_iso_node"),
    )

    # Pnode scores
    op.create_table(
        "pnode_scores",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("pipeline_run_id", sa.Integer, sa.ForeignKey("pipeline_runs.id")),
        sa.Column("pnode_id", sa.Integer, sa.ForeignKey("pnodes.id")),
        sa.Column("severity_score", sa.Float, nullable=False),
        sa.Column("tier", sa.String(20), nullable=False),
        sa.Column("avg_congestion", sa.Float),
        sa.Column("max_congestion", sa.Float),
        sa.Column("congested_hours_pct", sa.Float),
        sa.Column("constraint_loadshape", sa.JSON),
        sa.UniqueConstraint("pipeline_run_id", "pnode_id", name="uq_pnode_scores"),
    )

    # Data centers
    op.create_table(
        "data_centers",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("iso_id", sa.Integer, sa.ForeignKey("isos.id")),
        sa.Column("zone_id", sa.Integer, sa.ForeignKey("zones.id"), nullable=True),
        sa.Column("external_slug", sa.String(200), unique=True),
        sa.Column("facility_name", sa.String(200)),
        sa.Column("status", sa.String(30)),
        sa.Column("capacity_mw", sa.Float),
        sa.Column("lat", sa.Float),
        sa.Column("lon", sa.Float),
        sa.Column("state_code", sa.String(5)),
        sa.Column("county", sa.String(100)),
        sa.Column("operator", sa.String(200)),
        sa.Column("scraped_at", sa.DateTime(timezone=True)),
    )

    # DER recommendations
    op.create_table(
        "der_recommendations",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("pipeline_run_id", sa.Integer, sa.ForeignKey("pipeline_runs.id")),
        sa.Column("zone_id", sa.Integer, sa.ForeignKey("zones.id")),
        sa.Column("classification", sa.String(20)),
        sa.Column("rationale", sa.Text),
        sa.Column("congestion_value", sa.Float),
        sa.Column("primary_rec", sa.JSON),
        sa.Column("secondary_rec", sa.JSON),
        sa.Column("tertiary_rec", sa.JSON),
        sa.UniqueConstraint("pipeline_run_id", "zone_id", name="uq_der_recs"),
    )


def downgrade() -> None:
    """Drop all tables."""
    op.drop_table("der_recommendations")
    op.drop_table("data_centers")
    op.drop_table("pnode_scores")
    op.drop_table("pnodes")
    op.drop_table("zone_classifications")
    op.drop_table("pipeline_runs")
    op.drop_index("ix_zone_lmps_iso_month", "zone_lmps")
    op.drop_index("ix_zone_lmps_zone_ts", "zone_lmps")
    op.drop_table("zone_lmps")
    op.drop_table("zones")
    op.drop_table("isos")
