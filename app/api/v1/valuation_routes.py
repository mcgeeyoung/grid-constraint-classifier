"""API v1 routes for DER valuation, geo-resolution, and DER locations."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import ISO, Zone, Substation, DERLocation, DERValuation
from app.api.v1.spatial import BBox, parse_bbox
from app.schemas.valuation_schemas import (
    ProspectiveValuationRequest,
    CreateDERLocationRequest,
    GeoResolutionResponse,
    ValuationResponse,
    DERLocationResponse,
)
from core.geo_resolver import resolve, GeoResolution
from core.valuation_engine import compute_der_value
from core.der_profiles import get_eac_category

router = APIRouter(prefix="/api/v1")


@router.post("/valuations/prospective", response_model=ValuationResponse)
def prospective_valuation(
    req: ProspectiveValuationRequest,
    db: Session = Depends(get_db),
):
    """
    Compute the constraint-relief value of a hypothetical DER placement.

    Given a lat/lon, DER type, and capacity, resolves the location in the
    grid hierarchy and computes the dollar value of constraint relief at
    each level (zone, pnode, substation, feeder).
    """
    # Geo-resolve
    resolution = resolve(db, req.lat, req.lon)

    if not resolution.iso_id:
        raise HTTPException(
            404,
            f"Could not resolve coordinates ({req.lat}, {req.lon}) to any ISO/zone",
        )

    # Compute valuation
    val = compute_der_value(
        db=db,
        resolution=resolution,
        der_type=req.der_type,
        capacity_mw=req.capacity_mw,
        pipeline_run_id=req.pipeline_run_id,
    )

    geo = _resolution_to_response(resolution)

    return ValuationResponse(
        zone_congestion_value=val.zone_congestion_value,
        pnode_multiplier=val.pnode_multiplier,
        substation_loading_value=val.substation_loading_value,
        feeder_capacity_value=val.feeder_capacity_value,
        total_constraint_relief_value=val.total_constraint_relief_value,
        coincidence_factor=val.coincidence_factor,
        effective_capacity_mw=val.effective_capacity_mw,
        value_per_kw_year=val.value_per_kw_year,
        value_tier=val.value_tier,
        value_breakdown=val.value_breakdown,
        geo_resolution=geo,
    )


@router.get("/geo/resolve", response_model=GeoResolutionResponse)
def geo_resolve(
    lat: float = Query(..., description="Latitude"),
    lon: float = Query(..., description="Longitude"),
    db: Session = Depends(get_db),
):
    """
    Resolve a lat/lon coordinate to its position in the grid hierarchy.

    Returns ISO, zone, substation, feeder, circuit, and nearest pnode.
    """
    resolution = resolve(db, lat, lon)
    return _resolution_to_response(resolution)


@router.post("/der-locations", response_model=DERLocationResponse)
def create_der_location(
    req: CreateDERLocationRequest,
    db: Session = Depends(get_db),
):
    """
    Create a DER location record. Auto-resolves the grid hierarchy from lat/lon.
    """
    resolution = resolve(db, req.lat, req.lon)

    if not resolution.iso_id:
        raise HTTPException(
            404,
            f"Could not resolve coordinates ({req.lat}, {req.lon}) to any ISO/zone",
        )

    eac_category = get_eac_category(req.der_type)

    location = DERLocation(
        iso_id=resolution.iso_id,
        zone_id=resolution.zone_id,
        substation_id=resolution.substation_id,
        feeder_id=resolution.feeder_id,
        circuit_id=resolution.circuit_id,
        nearest_pnode_id=resolution.nearest_pnode_id,
        der_type=req.der_type,
        eac_category=eac_category,
        capacity_mw=req.capacity_mw,
        lat=req.lat,
        lon=req.lon,
        wattcarbon_asset_id=req.wattcarbon_asset_id,
        source=req.source,
    )
    db.add(location)
    db.commit()
    db.refresh(location)

    return DERLocationResponse(
        id=location.id,
        iso_code=resolution.iso_code,
        zone_code=resolution.zone_code,
        substation_name=resolution.substation_name,
        der_type=location.der_type,
        eac_category=location.eac_category,
        capacity_mw=location.capacity_mw,
        lat=location.lat,
        lon=location.lon,
        source=location.source,
        wattcarbon_asset_id=location.wattcarbon_asset_id,
        resolution_depth=resolution.resolution_depth,
    )


@router.get("/der-locations", response_model=list[DERLocationResponse])
def list_der_locations(
    iso_id: Optional[str] = Query(
        None, description="Comma-separated ISO codes (e.g. 'pjm,miso')",
    ),
    zone_code: Optional[str] = None,
    der_type: Optional[str] = None,
    source: Optional[str] = None,
    limit: int = Query(default=100, le=5000),
    offset: int = Query(default=0, ge=0),
    bbox: Optional[BBox] = Depends(parse_bbox),
    db: Session = Depends(get_db),
):
    """List DER locations with optional filters. Includes latest value_tier.

    Supports multi-ISO: ?iso_id=pjm,miso
    Supports bbox filtering: ?bbox=west,south,east,north
    """
    query = (
        db.query(DERLocation, ISO, Zone, Substation, DERValuation)
        .join(ISO, DERLocation.iso_id == ISO.id)
        .outerjoin(Zone, DERLocation.zone_id == Zone.id)
        .outerjoin(Substation, DERLocation.substation_id == Substation.id)
        .outerjoin(DERValuation, DERValuation.der_location_id == DERLocation.id)
    )

    if iso_id:
        codes = [c.strip().lower() for c in iso_id.split(",") if c.strip()]
        if len(codes) == 1:
            query = query.filter(ISO.iso_code == codes[0])
        else:
            query = query.filter(ISO.iso_code.in_(codes))
    if zone_code:
        query = query.filter(Zone.zone_code == zone_code)
    if der_type:
        query = query.filter(DERLocation.der_type == der_type)
    if source:
        query = query.filter(DERLocation.source == source)
    if bbox:
        query = query.filter(bbox.filter_column(DERLocation.geom))

    results = query.offset(offset).limit(limit).all()

    return [
        DERLocationResponse(
            id=loc.id,
            iso_code=iso.iso_code,
            zone_code=zone.zone_code if zone else None,
            substation_name=sub.substation_name if sub else None,
            der_type=loc.der_type,
            eac_category=loc.eac_category,
            capacity_mw=loc.capacity_mw,
            lat=loc.lat,
            lon=loc.lon,
            source=loc.source,
            wattcarbon_asset_id=loc.wattcarbon_asset_id,
            value_tier=val.value_tier if val else None,
        )
        for loc, iso, zone, sub, val in results
    ]


def _resolution_to_response(resolution: GeoResolution) -> GeoResolutionResponse:
    """Convert a GeoResolution dataclass to a Pydantic response."""
    return GeoResolutionResponse(
        lat=resolution.lat,
        lon=resolution.lon,
        iso_code=resolution.iso_code,
        zone_code=resolution.zone_code,
        substation_name=resolution.substation_name,
        substation_distance_km=resolution.substation_distance_km,
        nearest_pnode_name=resolution.nearest_pnode_name,
        pnode_distance_km=resolution.pnode_distance_km,
        feeder_id=resolution.feeder_id,
        circuit_id=resolution.circuit_id,
        resolution_depth=resolution.resolution_depth,
        confidence=resolution.confidence,
        errors=resolution.errors,
    )
