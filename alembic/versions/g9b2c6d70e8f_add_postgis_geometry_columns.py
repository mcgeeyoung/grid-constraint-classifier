"""Enable PostGIS and add native geometry columns to all spatial models.

Revision ID: g9b2c6d70e8f
Revises: f8a2b3c4d5e6
Create Date: 2026-02-27

Phase I-1.1: PostGIS migration - add GeoAlchemy2 geometry columns,
populate from existing lat/lon floats and geometry_json fields,
create GiST spatial indexes.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from geoalchemy2 import Geometry


# revision identifiers
revision: str = "g9b2c6d70e8f"
down_revision: Union[str, None] = "f8a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Enable PostGIS extension
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")

    # --- 1. Add geometry columns ---

    # zones: MULTIPOLYGON boundary from boundary_geojson (JSON)
    op.add_column(
        "zones",
        sa.Column("boundary_geom", Geometry("MULTIPOLYGON", srid=4326), nullable=True),
    )

    # pnodes: POINT from lat/lon
    op.add_column(
        "pnodes",
        sa.Column("geom", Geometry("POINT", srid=4326), nullable=True),
    )

    # data_centers: POINT from lat/lon
    op.add_column(
        "data_centers",
        sa.Column("geom", Geometry("POINT", srid=4326), nullable=True),
    )

    # substations: POINT from lat/lon
    op.add_column(
        "substations",
        sa.Column("geom", Geometry("POINT", srid=4326), nullable=True),
    )

    # transmission_lines: MULTILINESTRING from geometry_json (JSON)
    op.add_column(
        "transmission_lines",
        sa.Column("geom", Geometry("MULTILINESTRING", srid=4326), nullable=True),
    )

    # feeders: LINESTRING from geometry_json (JSON)
    op.add_column(
        "feeders",
        sa.Column("geom", Geometry("LINESTRING", srid=4326), nullable=True),
    )

    # circuits: POINT from lat/lon
    op.add_column(
        "circuits",
        sa.Column("geom", Geometry("POINT", srid=4326), nullable=True),
    )

    # der_locations: POINT from lat/lon
    op.add_column(
        "der_locations",
        sa.Column("geom", Geometry("POINT", srid=4326), nullable=True),
    )

    # --- 2. Populate geometry from existing data ---

    # Point geometries from lat/lon floats
    for table in ("pnodes", "data_centers", "substations", "circuits", "der_locations"):
        op.execute(
            f"""
            UPDATE {table}
            SET geom = ST_SetSRID(ST_MakePoint(lon, lat), 4326)
            WHERE lat IS NOT NULL AND lon IS NOT NULL
            """
        )

    # Zone boundaries from GeoJSON (JSON column -> geometry)
    op.execute(
        """
        UPDATE zones
        SET boundary_geom = ST_SetSRID(ST_GeomFromGeoJSON(boundary_geojson::text), 4326)
        WHERE boundary_geojson IS NOT NULL
        """
    )

    # Transmission lines from geometry_json (JSON column -> geometry)
    op.execute(
        """
        UPDATE transmission_lines
        SET geom = ST_SetSRID(ST_GeomFromGeoJSON(geometry_json::text), 4326)
        WHERE geometry_json IS NOT NULL
        """
    )

    # Feeders from geometry_json (JSON column -> geometry)
    op.execute(
        """
        UPDATE feeders
        SET geom = ST_SetSRID(ST_GeomFromGeoJSON(geometry_json::text), 4326)
        WHERE geometry_json IS NOT NULL
        """
    )

    # --- 3. Create GiST spatial indexes ---
    op.create_index(
        "ix_zones_boundary_geom", "zones", ["boundary_geom"],
        postgresql_using="gist",
    )
    op.create_index(
        "ix_pnodes_geom", "pnodes", ["geom"],
        postgresql_using="gist",
    )
    op.create_index(
        "ix_data_centers_geom", "data_centers", ["geom"],
        postgresql_using="gist",
    )
    op.create_index(
        "ix_substations_geom", "substations", ["geom"],
        postgresql_using="gist",
    )
    op.create_index(
        "ix_transmission_lines_geom", "transmission_lines", ["geom"],
        postgresql_using="gist",
    )
    op.create_index(
        "ix_feeders_geom", "feeders", ["geom"],
        postgresql_using="gist",
    )
    op.create_index(
        "ix_circuits_geom", "circuits", ["geom"],
        postgresql_using="gist",
    )
    op.create_index(
        "ix_der_locations_geom", "der_locations", ["geom"],
        postgresql_using="gist",
    )


def downgrade() -> None:
    # Drop indexes
    op.drop_index("ix_der_locations_geom", table_name="der_locations")
    op.drop_index("ix_circuits_geom", table_name="circuits")
    op.drop_index("ix_feeders_geom", table_name="feeders")
    op.drop_index("ix_transmission_lines_geom", table_name="transmission_lines")
    op.drop_index("ix_substations_geom", table_name="substations")
    op.drop_index("ix_data_centers_geom", table_name="data_centers")
    op.drop_index("ix_pnodes_geom", table_name="pnodes")
    op.drop_index("ix_zones_boundary_geom", table_name="zones")

    # Drop geometry columns
    op.drop_column("der_locations", "geom")
    op.drop_column("circuits", "geom")
    op.drop_column("feeders", "geom")
    op.drop_column("transmission_lines", "geom")
    op.drop_column("substations", "geom")
    op.drop_column("data_centers", "geom")
    op.drop_column("pnodes", "geom")
    op.drop_column("zones", "boundary_geom")

    # Note: not dropping postgis extension as other things may depend on it
