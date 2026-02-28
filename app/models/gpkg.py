"""GeoPackage-sourced infrastructure models (OSM data via USA.gpkg).

Separate tables from existing HIFLD/GRIP-sourced data to avoid schema
conflicts. Each table stores data with normalized units (kV, MW) and
PostGIS geometry columns with GiST indexes for spatial queries.

Source: USA.gpkg (1.7GB, EPSG:4326, OpenStreetMap-derived)
"""

from typing import Optional

from geoalchemy2 import Geometry
from sqlalchemy import Index, String, Float, Integer, Boolean, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class GPKGPowerLine(Base):
    """Transmission/distribution power line from GeoPackage (OSM).

    538K features. Geometry is LINESTRING in EPSG:4326.
    Voltage stored in kV (normalized from source volts).
    """

    __tablename__ = "gpkg_power_lines"
    __table_args__ = (
        Index("ix_gpkg_power_lines_max_voltage_kv", "max_voltage_kv"),
        Index("ix_gpkg_power_lines_operator", "operator"),
        Index("ix_gpkg_power_lines_geom", "geom", postgresql_using="gist"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    osm_id: Mapped[Optional[int]] = mapped_column(Integer)
    name: Mapped[Optional[str]] = mapped_column(String(300))
    ref: Mapped[Optional[str]] = mapped_column(String(100))
    operator: Mapped[Optional[str]] = mapped_column(String(300))
    max_voltage_kv: Mapped[Optional[float]] = mapped_column(Float)
    voltages: Mapped[Optional[str]] = mapped_column(String(200))
    circuits: Mapped[Optional[int]] = mapped_column(Integer)
    cables: Mapped[Optional[str]] = mapped_column(String(50))
    location: Mapped[Optional[str]] = mapped_column(String(50))
    construction: Mapped[Optional[bool]] = mapped_column(Boolean)
    disused: Mapped[Optional[bool]] = mapped_column(Boolean)
    frequency: Mapped[Optional[str]] = mapped_column(String(50))
    start_date: Mapped[Optional[str]] = mapped_column(String(50))
    geom = mapped_column(Geometry("LINESTRING", srid=4326), nullable=True)

    def __repr__(self) -> str:
        return f"<GPKGPowerLine(id={self.id}, name={self.name!r}, {self.max_voltage_kv}kV)>"


class GPKGSubstation(Base):
    """Substation from GeoPackage (OSM).

    68K features. Geometry is POLYGON/MULTIPOLYGON in EPSG:4326.
    Voltage stored in kV (normalized from source volts).
    Centroid lat/lon extracted from geometry for point queries.
    """

    __tablename__ = "gpkg_substations"
    __table_args__ = (
        Index("ix_gpkg_substations_substation_type", "substation_type"),
        Index("ix_gpkg_substations_max_voltage_kv", "max_voltage_kv"),
        Index("ix_gpkg_substations_operator", "operator"),
        Index("ix_gpkg_substations_geom", "geom", postgresql_using="gist"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    osm_id: Mapped[Optional[int]] = mapped_column(Integer)
    name: Mapped[Optional[str]] = mapped_column(String(300))
    ref: Mapped[Optional[str]] = mapped_column(String(100))
    operator: Mapped[Optional[str]] = mapped_column(String(300))
    substation_type: Mapped[Optional[str]] = mapped_column(String(100))
    max_voltage_kv: Mapped[Optional[float]] = mapped_column(Float)
    voltages: Mapped[Optional[str]] = mapped_column(String(200))
    frequency: Mapped[Optional[str]] = mapped_column(String(50))
    construction: Mapped[Optional[bool]] = mapped_column(Boolean)
    start_date: Mapped[Optional[str]] = mapped_column(String(50))
    centroid_lat: Mapped[Optional[float]] = mapped_column(Float)
    centroid_lon: Mapped[Optional[float]] = mapped_column(Float)
    geom = mapped_column(Geometry("GEOMETRY", srid=4326), nullable=True)

    def __repr__(self) -> str:
        return f"<GPKGSubstation(id={self.id}, name={self.name!r}, type={self.substation_type!r})>"


class GPKGPowerPlant(Base):
    """Power plant/generation facility from GeoPackage (OSM).

    15K features. Geometry is POLYGON/MULTIPOLYGON in EPSG:4326.
    Output stored in MW (normalized from source watts).
    """

    __tablename__ = "gpkg_power_plants"
    __table_args__ = (
        Index("ix_gpkg_power_plants_source", "source"),
        Index("ix_gpkg_power_plants_output_mw", "output_mw"),
        Index("ix_gpkg_power_plants_operator", "operator"),
        Index("ix_gpkg_power_plants_geom", "geom", postgresql_using="gist"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    osm_id: Mapped[Optional[int]] = mapped_column(Integer)
    name: Mapped[Optional[str]] = mapped_column(String(300))
    wikidata: Mapped[Optional[str]] = mapped_column(String(50))
    operator: Mapped[Optional[str]] = mapped_column(String(300))
    source: Mapped[Optional[str]] = mapped_column(String(100))
    method: Mapped[Optional[str]] = mapped_column(String(100))
    output_mw: Mapped[Optional[float]] = mapped_column(Float)
    construction: Mapped[Optional[bool]] = mapped_column(Boolean)
    start_date: Mapped[Optional[str]] = mapped_column(String(50))
    centroid_lat: Mapped[Optional[float]] = mapped_column(Float)
    centroid_lon: Mapped[Optional[float]] = mapped_column(Float)
    geom = mapped_column(Geometry("GEOMETRY", srid=4326), nullable=True)

    def __repr__(self) -> str:
        return f"<GPKGPowerPlant(id={self.id}, name={self.name!r}, source={self.source!r}, {self.output_mw}MW)>"
