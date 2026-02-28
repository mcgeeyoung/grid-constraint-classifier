"""Add hosting capacity tables: utilities, hc_ingestion_runs,
hosting_capacity_records, hosting_capacity_summaries.

Revision ID: i1d4e8f92a0b
Revises: h0c3d7e81f9a
Create Date: 2026-02-28
"""

from alembic import op
import sqlalchemy as sa
from geoalchemy2 import Geometry

# revision identifiers, used by Alembic
revision = "i1d4e8f92a0b"
down_revision = "h0c3d7e81f9a"
branch_labels = None
depends_on = None


def upgrade():
    # --- utilities ---
    op.create_table(
        "utilities",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("utility_code", sa.String(50), unique=True, nullable=False),
        sa.Column("utility_name", sa.String(200), nullable=False),
        sa.Column("parent_company", sa.String(200)),
        sa.Column("iso_id", sa.Integer, sa.ForeignKey("isos.id")),
        sa.Column("states", sa.JSON),
        sa.Column("data_source_type", sa.String(50), nullable=False),
        sa.Column("requires_auth", sa.Boolean, server_default="false"),
        sa.Column("service_url", sa.String(500)),
        sa.Column("last_ingested_at", sa.DateTime(timezone=True)),
        sa.Column("config_json", sa.JSON),
    )
    op.create_index("ix_utilities_iso_id", "utilities", ["iso_id"])

    # --- hc_ingestion_runs ---
    op.create_table(
        "hc_ingestion_runs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("utility_id", sa.Integer, sa.ForeignKey("utilities.id"), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("status", sa.String(20), server_default="running"),
        sa.Column("records_fetched", sa.Integer),
        sa.Column("records_written", sa.Integer),
        sa.Column("error_message", sa.String(1000)),
        sa.Column("source_url", sa.String(500)),
    )

    # --- hosting_capacity_records ---
    op.create_table(
        "hosting_capacity_records",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("utility_id", sa.Integer, sa.ForeignKey("utilities.id"), nullable=False),
        sa.Column(
            "ingestion_run_id", sa.Integer,
            sa.ForeignKey("hc_ingestion_runs.id"), nullable=False,
        ),
        # Feeder identification
        sa.Column("feeder_id_external", sa.String(200), nullable=False),
        sa.Column("feeder_name", sa.String(300)),
        sa.Column("substation_name", sa.String(300)),
        # Optional hierarchy links
        sa.Column("substation_id", sa.Integer, sa.ForeignKey("substations.id")),
        sa.Column("feeder_id", sa.Integer, sa.ForeignKey("feeders.id")),
        # Capacity (MW)
        sa.Column("hosting_capacity_mw", sa.Float),
        sa.Column("hosting_capacity_min_mw", sa.Float),
        sa.Column("hosting_capacity_max_mw", sa.Float),
        sa.Column("installed_dg_mw", sa.Float),
        sa.Column("queued_dg_mw", sa.Float),
        sa.Column("remaining_capacity_mw", sa.Float),
        # Constraint
        sa.Column("constraining_metric", sa.String(100)),
        # Feeder characteristics
        sa.Column("voltage_kv", sa.Float),
        sa.Column("phase_config", sa.String(20)),
        sa.Column("is_overhead", sa.Boolean),
        sa.Column("is_network", sa.Boolean),
        # Geometry
        sa.Column("centroid_lat", sa.Float),
        sa.Column("centroid_lon", sa.Float),
        sa.Column("geom", Geometry("POINT", srid=4326)),
        sa.Column("geometry_json", sa.JSON),
        # Provenance
        sa.Column("record_date", sa.Date),
        sa.Column("raw_attributes", sa.JSON),
        # Constraints
        sa.UniqueConstraint(
            "utility_id", "feeder_id_external", "ingestion_run_id",
            name="uq_hc_record",
        ),
    )
    op.create_index("ix_hc_utility", "hosting_capacity_records", ["utility_id"])
    op.create_index("ix_hc_ingestion_run", "hosting_capacity_records", ["ingestion_run_id"])
    op.create_index(
        "ix_hc_geom", "hosting_capacity_records", ["geom"],
        postgresql_using="gist",
    )

    # --- hosting_capacity_summaries ---
    op.create_table(
        "hosting_capacity_summaries",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "utility_id", sa.Integer,
            sa.ForeignKey("utilities.id"), unique=True, nullable=False,
        ),
        sa.Column("total_feeders", sa.Integer, server_default="0"),
        sa.Column("total_hosting_capacity_mw", sa.Float, server_default="0"),
        sa.Column("total_installed_dg_mw", sa.Float, server_default="0"),
        sa.Column("total_remaining_capacity_mw", sa.Float, server_default="0"),
        sa.Column("avg_utilization_pct", sa.Float),
        sa.Column("constrained_feeders_count", sa.Integer, server_default="0"),
        sa.Column("constraint_breakdown", sa.JSON),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade():
    op.drop_table("hosting_capacity_summaries")
    op.drop_table("hosting_capacity_records")
    op.drop_table("hc_ingestion_runs")
    op.drop_table("utilities")
