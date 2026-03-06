"""Valuation routes: "What DER is most valuable here?"

Endpoints for computing prospective DER valuations, comparing DER types,
and ranking locations by value.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth import require_api_key
from app.cache import cache_response
from app.database import get_db
from app.limiter import limiter
from app.models.iso import ISO
from app.models.constraint_profile import ConstraintProfile
from app.models.constraint_annotation import ConstraintAnnotation
from app.models.constraint_der_intersection import ConstraintDERIntersection
from app.models.der_profile import DERProfile
from app.models.location_value_stack import LocationValueStack
from app.schemas.new_valuation_schemas import (
    ProspectiveValuationRequest,
    ValueStackResponse,
    DERComparisonItem,
    DERComparisonResponse,
    LocationRankingResponse,
    BatchValuationRequest,
)
from app.schemas.constraint_schemas import AnnotationResponse

router = APIRouter(prefix="/api/valuations", tags=["valuations"])


@router.post("/prospective")
async def prospective_valuation(
    request_body: ProspectiveValuationRequest,
    db: Session = Depends(get_db),
):
    """Compute value stack for a DER at a lat/lon."""
    from core.geo_resolver import resolve

    resolution = resolve(db, request_body.lat, request_body.lon)
    zone_id = resolution.zone_id

    if not zone_id:
        raise HTTPException(
            status_code=400,
            detail="Could not resolve location to a grid zone")

    # Look up pre-computed value stack
    dp = (
        db.query(DERProfile)
        .filter_by(der_type=request_body.der_type, profile_source="canonical")
        .first()
    )
    if not dp:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown DER type: {request_body.der_type}")

    stack = (
        db.query(LocationValueStack)
        .filter_by(location_level="zone", location_id=zone_id,
                   der_profile_id=dp.id)
        .order_by(LocationValueStack.period_year.desc())
        .first()
    )

    # Get annotations
    profiles = (
        db.query(ConstraintProfile)
        .filter_by(location_level="zone", location_id=zone_id)
        .all()
    )
    all_annotations = []
    for cp in profiles:
        annots = db.query(ConstraintAnnotation).filter_by(
            constraint_profile_id=cp.id).all()
        all_annotations.extend(annots)

    if stack:
        return {
            "geo_resolution": {
                "lat": request_body.lat,
                "lon": request_body.lon,
                "iso_code": resolution.iso_code,
                "zone_code": resolution.zone_code,
                "substation_name": resolution.substation_name,
                "nearest_pnode_name": resolution.nearest_pnode_name,
                "feeder_id": resolution.feeder_id,
                "resolution_depth": resolution.resolution_depth or "zone",
                "constraints": [],
                "best_der": None,
                "total_value_per_kw_year": stack.total_value_per_kw_year,
            },
            "congestion_value_per_kw_year": stack.congestion_value_per_kw_year or 0.0,
            "loading_value_per_kw_year": stack.loading_value_per_kw_year or 0.0,
            "capacity_value_per_kw_year": stack.capacity_value_per_kw_year or 0.0,
            "import_stress_value_per_kw_year": stack.import_stress_value_per_kw_year or 0.0,
            "total_value_per_kw_year": stack.total_value_per_kw_year,
            "composite_coincidence_factor": stack.composite_coincidence_factor,
            "value_tier": stack.value_tier,
            "constraint_layers": stack.constraint_layers or [],
            "annotations": [
                {"id": a.id, "annotation_type": a.annotation_type,
                 "title": a.title, "summary": a.summary,
                 "planned_solution": a.planned_solution,
                 "deferral_value_estimate": a.deferral_value_estimate,
                 "source_url": a.source_url, "confidence": a.confidence}
                for a in all_annotations
            ],
        }

    # No pre-computed stack: return basic resolution
    return {
        "geo_resolution": {
            "lat": request_body.lat,
            "lon": request_body.lon,
            "iso_code": resolution.iso_code,
            "zone_code": resolution.zone_code,
            "resolution_depth": resolution.resolution_depth or "zone",
            "constraints": [],
            "best_der": None,
            "total_value_per_kw_year": None,
        },
        "congestion_value_per_kw_year": 0.0,
        "loading_value_per_kw_year": 0.0,
        "capacity_value_per_kw_year": 0.0,
        "import_stress_value_per_kw_year": 0.0,
        "total_value_per_kw_year": 0.0,
        "composite_coincidence_factor": 0.0,
        "value_tier": "low",
        "constraint_layers": [],
        "annotations": [],
    }


@router.get("/compare")
async def compare_der_types(
    lat: float = Query(...),
    lon: float = Query(...),
    db: Session = Depends(get_db),
):
    """Compare all DER types at a location."""
    from core.geo_resolver import resolve

    resolution = resolve(db, lat, lon)
    zone_id = resolution.zone_id

    if not zone_id:
        raise HTTPException(
            status_code=400,
            detail="Could not resolve location to a grid zone")

    stacks = (
        db.query(LocationValueStack, DERProfile)
        .join(DERProfile, LocationValueStack.der_profile_id == DERProfile.id)
        .filter(
            LocationValueStack.location_level == "zone",
            LocationValueStack.location_id == zone_id,
            DERProfile.profile_source == "canonical",
        )
        .order_by(LocationValueStack.total_value_per_kw_year.desc())
        .all()
    )

    comparisons = []
    for stack, dp in stacks:
        comparisons.append(DERComparisonItem(
            der_type=dp.der_type,
            eac_category=dp.eac_category,
            total_value_per_kw_year=stack.total_value_per_kw_year,
            coincidence_factor=stack.composite_coincidence_factor,
            value_tier=stack.value_tier,
            is_dispatchable=dp.is_dispatchable,
        ))

    return {
        "geo_resolution": {
            "lat": lat,
            "lon": lon,
            "iso_code": resolution.iso_code,
            "zone_code": resolution.zone_code,
            "resolution_depth": resolution.resolution_depth or "zone",
        },
        "comparisons": comparisons,
    }


@router.get("/rankings")
@cache_response("rankings", ttl=600)
async def value_rankings(
    iso_code: str = Query(...),
    der_type: str = Query(...),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    request: Request = None,
    db: Session = Depends(get_db),
):
    """Top locations by value for a given DER type."""
    iso = db.query(ISO).filter(func.lower(ISO.iso_code) == iso_code.lower()).first()
    if not iso:
        raise HTTPException(status_code=404, detail=f"ISO '{iso_code}' not found")

    dp = (
        db.query(DERProfile)
        .filter_by(der_type=der_type, profile_source="canonical")
        .first()
    )
    if not dp:
        raise HTTPException(status_code=400, detail=f"Unknown DER type: {der_type}")

    from app.models.zone import Zone

    rankings = (
        db.query(LocationValueStack, Zone)
        .join(Zone, LocationValueStack.location_id == Zone.id)
        .filter(
            LocationValueStack.location_level == "zone",
            LocationValueStack.der_profile_id == dp.id,
            Zone.iso_id == iso.id,
        )
        .order_by(LocationValueStack.total_value_per_kw_year.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    return [
        LocationRankingResponse(
            location_level="zone",
            location_id=zone.id,
            location_name=zone.zone_name or zone.zone_code,
            lat=zone.centroid_lat,
            lon=zone.centroid_lon,
            total_value_per_kw_year=stack.total_value_per_kw_year,
            value_tier=stack.value_tier,
            coincidence_factor=stack.composite_coincidence_factor,
        )
        for stack, zone in rankings
    ]


@router.post("/batch")
@limiter.limit("10/minute")
async def batch_valuation(
    request_body: BatchValuationRequest,
    request: Request = None,
    api_key: str = Depends(require_api_key),
    db: Session = Depends(get_db),
):
    """Batch valuation for up to 100 locations."""
    results = []
    for item in request_body.items:
        try:
            result = await prospective_valuation(item, db)
            results.append(result)
        except HTTPException:
            results.append({"error": f"Could not resolve ({item.lat}, {item.lon})"})
    return results
