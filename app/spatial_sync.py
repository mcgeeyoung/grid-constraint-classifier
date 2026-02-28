"""Sync lat/lon floats with PostGIS geom columns on INSERT/UPDATE.

Call `register_spatial_sync()` at app startup to attach SQLAlchemy event
listeners that automatically populate the `geom` column from `lat`/`lon`
(and vice versa) whenever a spatial model is inserted or updated.

For models with JSON geometry (zones, transmission_lines, feeders),
the geom column is populated from the JSON field and should be updated
via migration or manual sync rather than automatic events.
"""

from geoalchemy2.shape import from_shape, to_shape
from shapely.geometry import Point
from sqlalchemy import event

from app.models import (
    Pnode, DataCenter, Substation, Circuit, DERLocation,
)

# Models that have lat, lon, and geom (POINT) columns
POINT_MODELS = [Pnode, DataCenter, Substation, Circuit, DERLocation]


def _sync_point_geom(mapper, connection, target):
    """Before insert/update: if lat/lon changed, update geom."""
    if target.lat is not None and target.lon is not None:
        target.geom = from_shape(Point(target.lon, target.lat), srid=4326)
    elif target.lat is None and target.lon is None:
        target.geom = None


def register_spatial_sync():
    """Register SQLAlchemy event listeners for all spatial models."""
    for model in POINT_MODELS:
        event.listen(model, "before_insert", _sync_point_geom)
        event.listen(model, "before_update", _sync_point_geom)
