"""Add GeoPackage infrastructure tables (power lines, substations, plants).
Geometry columns omitted (PostGIS not available on PG 16.6); add via
a future migration once PostGIS is installed.

Revision ID: p8k1e3f69g7h
Revises: o7j0e4f58g6h
Create Date: 2026-02-28
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic
revision = "p8k1e3f69g7h"
down_revision = "o7j0e4f58g6h"
branch_labels = None
depends_on = None


def upgrade():
    # --- gpkg_power_lines ---
    op.create_table(
        "gpkg_power_lines",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("osm_id", sa.Integer(), nullable=True),
        sa.Column("name", sa.String(300), nullable=True),
        sa.Column("ref", sa.String(100), nullable=True),
        sa.Column("operator", sa.String(300), nullable=True),
        sa.Column("max_voltage_kv", sa.Float(), nullable=True),
        sa.Column("voltages", sa.String(200), nullable=True),
        sa.Column("circuits", sa.Integer(), nullable=True),
        sa.Column("cables", sa.String(50), nullable=True),
        sa.Column("location", sa.String(50), nullable=True),
        sa.Column("construction", sa.Boolean(), nullable=True),
        sa.Column("disused", sa.Boolean(), nullable=True),
        sa.Column("frequency", sa.String(50), nullable=True),
        sa.Column("start_date", sa.String(50), nullable=True),
    )
    op.create_index("ix_gpkg_power_lines_max_voltage_kv", "gpkg_power_lines", ["max_voltage_kv"])
    op.create_index("ix_gpkg_power_lines_operator", "gpkg_power_lines", ["operator"])

    # --- gpkg_substations ---
    op.create_table(
        "gpkg_substations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("osm_id", sa.Integer(), nullable=True),
        sa.Column("name", sa.String(300), nullable=True),
        sa.Column("ref", sa.String(100), nullable=True),
        sa.Column("operator", sa.String(300), nullable=True),
        sa.Column("substation_type", sa.String(100), nullable=True),
        sa.Column("max_voltage_kv", sa.Float(), nullable=True),
        sa.Column("voltages", sa.String(200), nullable=True),
        sa.Column("frequency", sa.String(50), nullable=True),
        sa.Column("construction", sa.Boolean(), nullable=True),
        sa.Column("start_date", sa.String(50), nullable=True),
        sa.Column("centroid_lat", sa.Float(), nullable=True),
        sa.Column("centroid_lon", sa.Float(), nullable=True),
    )
    op.create_index("ix_gpkg_substations_substation_type", "gpkg_substations", ["substation_type"])
    op.create_index("ix_gpkg_substations_max_voltage_kv", "gpkg_substations", ["max_voltage_kv"])
    op.create_index("ix_gpkg_substations_operator", "gpkg_substations", ["operator"])

    # --- gpkg_power_plants ---
    op.create_table(
        "gpkg_power_plants",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("osm_id", sa.Integer(), nullable=True),
        sa.Column("name", sa.String(300), nullable=True),
        sa.Column("wikidata", sa.String(50), nullable=True),
        sa.Column("operator", sa.String(300), nullable=True),
        sa.Column("source", sa.String(100), nullable=True),
        sa.Column("method", sa.String(100), nullable=True),
        sa.Column("output_mw", sa.Float(), nullable=True),
        sa.Column("construction", sa.Boolean(), nullable=True),
        sa.Column("start_date", sa.String(50), nullable=True),
        sa.Column("centroid_lat", sa.Float(), nullable=True),
        sa.Column("centroid_lon", sa.Float(), nullable=True),
    )
    op.create_index("ix_gpkg_power_plants_source", "gpkg_power_plants", ["source"])
    op.create_index("ix_gpkg_power_plants_output_mw", "gpkg_power_plants", ["output_mw"])
    op.create_index("ix_gpkg_power_plants_operator", "gpkg_power_plants", ["operator"])


def downgrade():
    op.drop_index("ix_gpkg_power_plants_operator", table_name="gpkg_power_plants")
    op.drop_index("ix_gpkg_power_plants_output_mw", table_name="gpkg_power_plants")
    op.drop_index("ix_gpkg_power_plants_source", table_name="gpkg_power_plants")
    op.drop_table("gpkg_power_plants")

    op.drop_index("ix_gpkg_substations_operator", table_name="gpkg_substations")
    op.drop_index("ix_gpkg_substations_max_voltage_kv", table_name="gpkg_substations")
    op.drop_index("ix_gpkg_substations_substation_type", table_name="gpkg_substations")
    op.drop_table("gpkg_substations")

    op.drop_index("ix_gpkg_power_lines_operator", table_name="gpkg_power_lines")
    op.drop_index("ix_gpkg_power_lines_max_voltage_kv", table_name="gpkg_power_lines")
    op.drop_table("gpkg_power_lines")
