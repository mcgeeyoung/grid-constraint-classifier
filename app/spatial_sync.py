"""Sync lat/lon floats with PostGIS geom columns on INSERT/UPDATE.

Call `register_spatial_sync()` at app startup to attach SQLAlchemy event
listeners that automatically populate the `geom` column from `lat`/`lon`
(and vice versa) whenever a spatial model is inserted or updated.

Covers three patterns:
  1. Standard POINT models (lat/lon -> geom)
  2. Centroid models (centroid_lat/centroid_lon -> geom)
  3. Alternate-name models (latitude/longitude -> geom)

For models with JSON geometry (zones, transmission_lines, feeders),
the geom column is populated from the JSON field via migration or
the _sync_json_geom helper (called explicitly, not auto-triggered).
"""

from geoalchemy2.shape import from_shape
from shapely.geometry import Point, shape
from sqlalchemy import event

from app.models import (
    Pnode, DataCenter, Substation, Circuit, DERLocation,
    HostingCapacityRecord, InterconnectionQueue,
)

# Pattern 1: Models with standard lat/lon -> geom
POINT_MODELS = [Pnode, DataCenter, Substation, Circuit, DERLocation]

# Pattern 2: Models with centroid_lat/centroid_lon -> geom
CENTROID_MODELS = [HostingCapacityRecord]

# Pattern 3: Models with latitude/longitude -> geom
LATLONG_MODELS = [InterconnectionQueue]


def _sync_point_geom(mapper, connection, target):
    """Before insert/update: sync lat/lon -> geom."""
    if target.lat is not None and target.lon is not None:
        target.geom = from_shape(Point(target.lon, target.lat), srid=4326)
    elif target.lat is None and target.lon is None:
        target.geom = None


def _sync_centroid_geom(mapper, connection, target):
    """Before insert/update: sync centroid_lat/centroid_lon -> geom."""
    if target.centroid_lat is not None and target.centroid_lon is not None:
        target.geom = from_shape(
            Point(target.centroid_lon, target.centroid_lat), srid=4326
        )
    elif target.centroid_lat is None and target.centroid_lon is None:
        target.geom = None


def _sync_latlong_geom(mapper, connection, target):
    """Before insert/update: sync latitude/longitude -> geom."""
    if target.latitude is not None and target.longitude is not None:
        target.geom = from_shape(
            Point(target.longitude, target.latitude), srid=4326
        )
    elif target.latitude is None and target.longitude is None:
        target.geom = None


def sync_json_geom(target, json_attr: str, geom_attr: str = "geom"):
    """Sync a GeoJSON dict column to a PostGIS geometry column.

    Call explicitly when updating JSON geometry on Zone, TransmissionLine,
    or Feeder models. Not auto-triggered via events because JSON geometry
    changes are less frequent and may need custom handling.

    Usage:
        zone.boundary_geojson = new_geojson
        sync_json_geom(zone, "boundary_geojson", "boundary_geom")
    """
    geojson = getattr(target, json_attr)
    if geojson:
        try:
            geom = shape(geojson)
            setattr(target, geom_attr, from_shape(geom, srid=4326))
        except Exception:
            setattr(target, geom_attr, None)
    else:
        setattr(target, geom_attr, None)


def register_spatial_sync():
    """Register SQLAlchemy event listeners for all spatial models."""
    for model in POINT_MODELS:
        event.listen(model, "before_insert", _sync_point_geom)
        event.listen(model, "before_update", _sync_point_geom)

    for model in CENTROID_MODELS:
        event.listen(model, "before_insert", _sync_centroid_geom)
        event.listen(model, "before_update", _sync_centroid_geom)

    for model in LATLONG_MODELS:
        event.listen(model, "before_insert", _sync_latlong_geom)
        event.listen(model, "before_update", _sync_latlong_geom)
