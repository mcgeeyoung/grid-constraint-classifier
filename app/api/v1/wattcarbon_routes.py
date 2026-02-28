"""API v1 routes for WattCarbon asset integration."""

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import DERLocation, DERValuation, ISO, Zone, Substation, Pnode
from app.schemas.wattcarbon_schemas import (
    WattCarbonAssetResponse,
    WattCarbonAssetDetailResponse,
    ProspectiveValuationResponse,
    RetrospectiveValuationRequest,
    RetrospectiveValuationResponse,
)
from core.geo_resolver import resolve, haversine_km
from core.valuation_engine import compute_der_value
from core.retrospective_valuator import compute_retrospective_value
from adapters.wattcarbon_client import WattCarbonClient

router = APIRouter(prefix="/api/v1/wattcarbon")


@router.get("/assets", response_model=list[WattCarbonAssetResponse])
def list_wattcarbon_assets(
    iso_code: Optional[str] = None,
    der_type: Optional[str] = None,
    limit: int = Query(default=100, le=5000),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    """List synced WattCarbon assets (DERLocations with source=wattcarbon)."""
    query = (
        db.query(DERLocation, ISO, Zone, Substation)
        .join(ISO, DERLocation.iso_id == ISO.id)
        .outerjoin(Zone, DERLocation.zone_id == Zone.id)
        .outerjoin(Substation, DERLocation.substation_id == Substation.id)
        .filter(DERLocation.source == "wattcarbon")
    )

    if iso_code:
        query = query.filter(ISO.iso_code == iso_code.lower())
    if der_type:
        query = query.filter(DERLocation.der_type == der_type)

    results = query.offset(offset).limit(limit).all()

    return [
        WattCarbonAssetResponse(
            id=loc.id,
            wattcarbon_asset_id=loc.wattcarbon_asset_id,
            iso_code=iso.iso_code,
            zone_code=zone.zone_code if zone else None,
            substation_name=sub.substation_name if sub else None,
            der_type=loc.der_type,
            eac_category=loc.eac_category,
            capacity_mw=loc.capacity_mw,
            lat=loc.lat,
            lon=loc.lon,
        )
        for loc, iso, zone, sub in results
    ]


@router.get("/assets/{wattcarbon_asset_id}", response_model=WattCarbonAssetDetailResponse)
def get_wattcarbon_asset(
    wattcarbon_asset_id: str,
    db: Session = Depends(get_db),
):
    """Get a single WattCarbon asset with valuation data."""
    loc = (
        db.query(DERLocation)
        .filter(
            DERLocation.wattcarbon_asset_id == wattcarbon_asset_id,
            DERLocation.source == "wattcarbon",
        )
        .first()
    )

    if not loc:
        raise HTTPException(404, f"WattCarbon asset {wattcarbon_asset_id} not found")

    iso = db.query(ISO).get(loc.iso_id)
    zone = db.query(Zone).get(loc.zone_id) if loc.zone_id else None
    sub = db.query(Substation).get(loc.substation_id) if loc.substation_id else None
    pnode = db.query(Pnode).get(loc.nearest_pnode_id) if loc.nearest_pnode_id else None

    pnode_dist = None
    if pnode and loc.lat and loc.lon and pnode.lat and pnode.lon:
        pnode_dist = round(haversine_km(loc.lat, loc.lon, pnode.lat, pnode.lon), 2)

    # Get latest prospective valuation
    latest_val = (
        db.query(DERValuation)
        .filter(DERValuation.der_location_id == loc.id)
        .order_by(DERValuation.id.desc())
        .first()
    )
    val_dict = None
    if latest_val:
        val_dict = {
            "total_constraint_relief_value": latest_val.total_constraint_relief_value,
            "value_tier": latest_val.value_tier,
            "coincidence_factor": latest_val.coincidence_factor,
            "value_breakdown": latest_val.value_breakdown,
        }

    # Get latest retrospective valuation
    retro_val = (
        db.query(DERValuation)
        .filter(
            DERValuation.der_location_id == loc.id,
            DERValuation.actual_constraint_relief_value.isnot(None),
        )
        .order_by(DERValuation.id.desc())
        .first()
    )
    retro_dict = None
    if retro_val:
        retro_dict = {
            "actual_savings_mwh": retro_val.actual_savings_mwh,
            "actual_constraint_relief_value": retro_val.actual_constraint_relief_value,
            "retrospective_start": retro_val.retrospective_start.isoformat() if retro_val.retrospective_start else None,
            "retrospective_end": retro_val.retrospective_end.isoformat() if retro_val.retrospective_end else None,
        }

    return WattCarbonAssetDetailResponse(
        id=loc.id,
        wattcarbon_asset_id=loc.wattcarbon_asset_id,
        iso_code=iso.iso_code if iso else None,
        zone_code=zone.zone_code if zone else None,
        substation_name=sub.substation_name if sub else None,
        der_type=loc.der_type,
        eac_category=loc.eac_category,
        capacity_mw=loc.capacity_mw,
        lat=loc.lat,
        lon=loc.lon,
        feeder_id=loc.feeder_id,
        circuit_id=loc.circuit_id,
        nearest_pnode_name=pnode.node_name if pnode else None,
        pnode_distance_km=pnode_dist,
        latest_valuation=val_dict,
        latest_retrospective=retro_dict,
    )


@router.get(
    "/assets/{wattcarbon_asset_id}/valuation",
    response_model=ProspectiveValuationResponse,
)
def get_asset_valuation(
    wattcarbon_asset_id: str,
    pipeline_run_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    """Compute prospective valuation for a WattCarbon asset."""
    loc = (
        db.query(DERLocation)
        .filter(
            DERLocation.wattcarbon_asset_id == wattcarbon_asset_id,
            DERLocation.source == "wattcarbon",
        )
        .first()
    )

    if not loc:
        raise HTTPException(404, f"WattCarbon asset {wattcarbon_asset_id} not found")

    resolution = resolve(db, loc.lat, loc.lon)
    if not resolution.iso_id:
        raise HTTPException(
            404,
            f"Could not resolve asset location ({loc.lat}, {loc.lon}) to any ISO",
        )

    val = compute_der_value(
        db=db,
        resolution=resolution,
        der_type=loc.der_type,
        capacity_mw=loc.capacity_mw,
        pipeline_run_id=pipeline_run_id,
    )

    return ProspectiveValuationResponse(
        wattcarbon_asset_id=wattcarbon_asset_id,
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
    )


@router.post(
    "/assets/{wattcarbon_asset_id}/retrospective",
    response_model=RetrospectiveValuationResponse,
)
def compute_retrospective(
    wattcarbon_asset_id: str,
    req: RetrospectiveValuationRequest,
    db: Session = Depends(get_db),
):
    """Compute retrospective valuation from actual metered savings."""
    loc = (
        db.query(DERLocation)
        .filter(
            DERLocation.wattcarbon_asset_id == wattcarbon_asset_id,
            DERLocation.source == "wattcarbon",
        )
        .first()
    )

    if not loc:
        raise HTTPException(404, f"WattCarbon asset {wattcarbon_asset_id} not found")

    client = WattCarbonClient()

    start_dt = datetime.combine(req.start, datetime.min.time(), tzinfo=timezone.utc)
    end_dt = datetime.combine(req.end, datetime.min.time(), tzinfo=timezone.utc)

    retro = compute_retrospective_value(
        db=db,
        wattcarbon_client=client,
        der_location=loc,
        start=start_dt,
        end=end_dt,
        pipeline_run_id=req.pipeline_run_id,
    )

    # Persist the retrospective result on the latest DERValuation record
    existing_val = (
        db.query(DERValuation)
        .filter(DERValuation.der_location_id == loc.id)
        .order_by(DERValuation.id.desc())
        .first()
    )

    if existing_val:
        existing_val.actual_savings_mwh = retro.actual_savings_mwh
        existing_val.actual_constraint_relief_value = retro.actual_constraint_relief_value
        existing_val.actual_zone_congestion_value = retro.actual_zone_congestion_value
        existing_val.actual_substation_value = retro.actual_substation_value
        existing_val.actual_feeder_value = retro.actual_feeder_value
        existing_val.retrospective_start = retro.retrospective_start
        existing_val.retrospective_end = retro.retrospective_end
        db.commit()

    return RetrospectiveValuationResponse(
        wattcarbon_asset_id=wattcarbon_asset_id,
        actual_savings_mwh=retro.actual_savings_mwh,
        actual_constraint_relief_value=retro.actual_constraint_relief_value,
        actual_zone_congestion_value=retro.actual_zone_congestion_value,
        actual_substation_value=retro.actual_substation_value,
        actual_feeder_value=retro.actual_feeder_value,
        retrospective_start=retro.retrospective_start,
        retrospective_end=retro.retrospective_end,
    )
