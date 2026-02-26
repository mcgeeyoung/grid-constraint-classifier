"""
Geo-resolver: maps lat/lon to position in the grid hierarchy.

Given a coordinate, resolves to {iso, zone, substation, feeder, circuit,
nearest_pnode} using spatial lookups (point-in-polygon for zones,
nearest-neighbor haversine for substations/pnodes).
"""

import logging
from dataclasses import dataclass, field
from math import radians, sin, cos, sqrt, atan2
from typing import Optional

from sqlalchemy.orm import Session

from app.models import ISO, Zone, Substation, Pnode, Feeder, Circuit

logger = logging.getLogger(__name__)

# Maximum distance thresholds (km)
SUBSTATION_MAX_DISTANCE_KM = 30.0
PNODE_MAX_DISTANCE_KM = 50.0
FEEDER_MAX_DISTANCE_KM = 10.0


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two points in km."""
    R = 6371.0
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return R * 2 * atan2(sqrt(a), sqrt(1 - a))


@dataclass
class GeoResolution:
    """Result of resolving a lat/lon to the grid hierarchy."""
    lat: float
    lon: float
    iso_id: Optional[int] = None
    iso_code: Optional[str] = None
    zone_id: Optional[int] = None
    zone_code: Optional[str] = None
    substation_id: Optional[int] = None
    substation_name: Optional[str] = None
    substation_distance_km: Optional[float] = None
    feeder_id: Optional[int] = None
    circuit_id: Optional[int] = None
    nearest_pnode_id: Optional[int] = None
    nearest_pnode_name: Optional[str] = None
    pnode_distance_km: Optional[float] = None
    resolution_depth: str = "none"  # none/iso/zone/substation/feeder/circuit
    confidence: str = "low"  # low/medium/high
    errors: list[str] = field(default_factory=list)


def resolve(db: Session, lat: float, lon: float) -> GeoResolution:
    """
    Resolve a lat/lon coordinate to the full grid hierarchy.

    Resolution order:
    1. Zone: point-in-polygon using boundary_geojson (fallback: nearest centroid)
    2. ISO: derived from zone
    3. Substation: nearest by haversine within threshold
    4. Feeder/Circuit: nearest with geometry (or null if unavailable)
    5. Nearest pnode: haversine to Pnode.lat/lon

    Returns GeoResolution with resolution_depth indicating finest level resolved.
    """
    result = GeoResolution(lat=lat, lon=lon)

    # Step 1: Resolve zone (point-in-polygon)
    zone = _resolve_zone(db, lat, lon)
    if zone:
        result.zone_id = zone.id
        result.zone_code = zone.zone_code
        result.iso_id = zone.iso_id
        result.iso_code = zone.iso.iso_code if zone.iso else None
        result.resolution_depth = "zone"
        result.confidence = "high"
    else:
        # Fallback: nearest zone centroid
        zone = _nearest_zone_by_centroid(db, lat, lon)
        if zone:
            result.zone_id = zone.id
            result.zone_code = zone.zone_code
            result.iso_id = zone.iso_id
            result.iso_code = zone.iso.iso_code if zone.iso else None
            result.resolution_depth = "zone"
            result.confidence = "medium"
            result.errors.append("Zone resolved by nearest centroid, not polygon containment")

    if not result.iso_id:
        result.errors.append("Could not resolve to any ISO/zone")
        return result

    # Step 2: Resolve nearest substation within threshold
    sub, sub_dist = _nearest_substation(db, lat, lon, result.iso_id)
    if sub:
        result.substation_id = sub.id
        result.substation_name = sub.substation_name
        result.substation_distance_km = round(sub_dist, 2)
        result.resolution_depth = "substation"

    # Step 3: Resolve nearest pnode
    pnode, pnode_dist = _nearest_pnode(db, lat, lon, result.iso_id)
    if pnode:
        result.nearest_pnode_id = pnode.id
        result.nearest_pnode_name = pnode.node_name
        result.pnode_distance_km = round(pnode_dist, 2)

    # Step 4: Resolve feeder (if substation resolved)
    if result.substation_id:
        feeder = _nearest_feeder(db, lat, lon, result.substation_id)
        if feeder:
            result.feeder_id = feeder.id
            result.resolution_depth = "feeder"

            # Step 5: Resolve circuit (if feeder resolved)
            circuit = _nearest_circuit(db, lat, lon, feeder.id)
            if circuit:
                result.circuit_id = circuit.id
                result.resolution_depth = "circuit"

    # Confidence based on resolution depth and distances
    if result.resolution_depth in ("feeder", "circuit"):
        result.confidence = "high"
    elif result.resolution_depth == "substation" and sub_dist and sub_dist < 10.0:
        result.confidence = "high"
    elif result.resolution_depth == "substation":
        result.confidence = "medium"

    return result


def _resolve_zone(db: Session, lat: float, lon: float) -> Optional[Zone]:
    """Point-in-polygon zone lookup using boundary_geojson."""
    try:
        from shapely.geometry import shape, Point
    except ImportError:
        logger.warning("shapely not installed, skipping polygon zone resolution")
        return None

    point = Point(lon, lat)  # GeoJSON is (lon, lat)

    zones = db.query(Zone).filter(Zone.boundary_geojson.isnot(None)).all()
    for zone in zones:
        try:
            polygon = shape(zone.boundary_geojson)
            if polygon.contains(point):
                return zone
        except Exception:
            continue

    return None


def _nearest_zone_by_centroid(db: Session, lat: float, lon: float) -> Optional[Zone]:
    """Fallback: find nearest zone by centroid distance."""
    zones = db.query(Zone).filter(
        Zone.centroid_lat.isnot(None),
        Zone.centroid_lon.isnot(None),
    ).all()

    best_zone = None
    best_dist = float("inf")

    for zone in zones:
        dist = haversine_km(lat, lon, zone.centroid_lat, zone.centroid_lon)
        if dist < best_dist:
            best_dist = dist
            best_zone = zone

    return best_zone


def _nearest_substation(
    db: Session, lat: float, lon: float, iso_id: int,
) -> tuple[Optional[Substation], Optional[float]]:
    """Find nearest substation within threshold."""
    substations = db.query(Substation).filter(
        Substation.iso_id == iso_id,
        Substation.lat.isnot(None),
        Substation.lon.isnot(None),
    ).all()

    best = None
    best_dist = float("inf")

    for sub in substations:
        dist = haversine_km(lat, lon, sub.lat, sub.lon)
        if dist < best_dist:
            best_dist = dist
            best = sub

    if best and best_dist <= SUBSTATION_MAX_DISTANCE_KM:
        return best, best_dist
    return None, None


def _nearest_pnode(
    db: Session, lat: float, lon: float, iso_id: int,
) -> tuple[Optional[Pnode], Optional[float]]:
    """Find nearest pnode within threshold."""
    pnodes = db.query(Pnode).filter(
        Pnode.iso_id == iso_id,
        Pnode.lat.isnot(None),
        Pnode.lon.isnot(None),
    ).all()

    best = None
    best_dist = float("inf")

    for pnode in pnodes:
        dist = haversine_km(lat, lon, pnode.lat, pnode.lon)
        if dist < best_dist:
            best_dist = dist
            best = pnode

    if best and best_dist <= PNODE_MAX_DISTANCE_KM:
        return best, best_dist
    return None, None


def _nearest_feeder(
    db: Session, lat: float, lon: float, substation_id: int,
) -> Optional[Feeder]:
    """Find nearest feeder for a given substation. Returns None if no feeders exist."""
    feeders = db.query(Feeder).filter(
        Feeder.substation_id == substation_id,
    ).all()

    if not feeders:
        return None

    # If only one feeder, return it
    if len(feeders) == 1:
        return feeders[0]

    # Multiple feeders: pick by geometry proximity if available
    # For now, return the first (feeder-level geo resolution is Phase 2)
    return feeders[0]


def _nearest_circuit(
    db: Session, lat: float, lon: float, feeder_id: int,
) -> Optional[Circuit]:
    """Find nearest circuit on a feeder."""
    circuits = db.query(Circuit).filter(
        Circuit.feeder_id == feeder_id,
        Circuit.lat.isnot(None),
        Circuit.lon.isnot(None),
    ).all()

    if not circuits:
        return None

    best = None
    best_dist = float("inf")

    for circuit in circuits:
        dist = haversine_km(lat, lon, circuit.lat, circuit.lon)
        if dist < best_dist:
            best_dist = dist
            best = circuit

    return best
