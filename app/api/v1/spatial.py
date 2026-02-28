"""Spatial query helpers for PostGIS-based bbox filtering."""

from typing import Optional

from fastapi import Query
from geoalchemy2 import Geometry
from geoalchemy2.functions import ST_MakeEnvelope, ST_Intersects
from sqlalchemy.orm import QueryableAttribute


class BBox:
    """Parsed bounding box with convenience methods."""

    def __init__(self, west: float, south: float, east: float, north: float):
        self.west = west
        self.south = south
        self.east = east
        self.north = north

    def envelope(self, srid: int = 4326):
        """Return a PostGIS ST_MakeEnvelope expression."""
        return ST_MakeEnvelope(self.west, self.south, self.east, self.north, srid)

    def filter_column(self, geom_col):
        """Return a SQLAlchemy filter clause: geom && ST_MakeEnvelope(...)."""
        return ST_Intersects(geom_col, self.envelope())


def parse_bbox(
    bbox: Optional[str] = Query(
        None,
        description="Bounding box as west,south,east,north (EPSG:4326). Example: -122.5,37.0,-121.5,38.0",
    ),
) -> Optional[BBox]:
    """FastAPI dependency that parses a bbox query parameter."""
    if bbox is None:
        return None

    parts = bbox.split(",")
    if len(parts) != 4:
        from fastapi import HTTPException
        raise HTTPException(
            400,
            "bbox must have exactly 4 comma-separated values: west,south,east,north",
        )

    try:
        west, south, east, north = (float(p.strip()) for p in parts)
    except ValueError:
        from fastapi import HTTPException
        raise HTTPException(400, "bbox values must be numeric")

    if not (-180 <= west <= 180 and -180 <= east <= 180):
        from fastapi import HTTPException
        raise HTTPException(400, "bbox longitude must be between -180 and 180")
    if not (-90 <= south <= 90 and -90 <= north <= 90):
        from fastapi import HTTPException
        raise HTTPException(400, "bbox latitude must be between -90 and 90")

    return BBox(west, south, east, north)
