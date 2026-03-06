"""Constraint routes: "What constraints exist here?"

Endpoints for discovering grid constraints at specific locations,
browsing zone constraint summaries, and viewing constraint profiles.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app.cache import cache_response
from app.database import get_db
from app.models.iso import ISO
from app.models.zone import Zone
from app.models.zone_lmp import ZoneLMP
from app.models.constraint_profile import ConstraintProfile
from app.models.constraint_annotation import ConstraintAnnotation
from app.models.constraint_der_intersection import ConstraintDERIntersection
from app.models.der_profile import DERProfile
from app.models.location_value_stack import LocationValueStack
from app.schemas.constraint_schemas import (
    ConstraintProfileResponse,
    ZoneConstraintSummaryResponse,
    GeoResolutionResponse,
    AnnotationResponse,
)

router = APIRouter(prefix="/api", tags=["constraints"])


@router.get("/resolve")
@cache_response("geo-resolve", ttl=300)
async def resolve_location(
    lat: float = Query(...),
    lon: float = Query(...),
    request: Request = None,
    db: Session = Depends(get_db),
):
    """Resolve lat/lon to grid hierarchy + constraint summary."""
    from core.geo_resolver import resolve

    resolution = resolve(db, lat, lon)

    # Get constraint profiles at the resolved location
    constraints = []
    best_der = None
    total_value = None

    if resolution.zone_id:
        zone_profiles = (
            db.query(ConstraintProfile)
            .filter_by(location_level="zone", location_id=resolution.zone_id)
            .all()
        )
        for cp in zone_profiles:
            annotations = db.query(ConstraintAnnotation).filter_by(
                constraint_profile_id=cp.id).all()
            constraints.append({
                "id": cp.id,
                "location_level": cp.location_level,
                "location_id": cp.location_id,
                "constraint_type": cp.constraint_type,
                "period_year": cp.period_year,
                "profile_12x24": cp.profile_12x24,
                "peak_intensity": cp.peak_intensity,
                "peak_month": cp.peak_month,
                "peak_hour": cp.peak_hour,
                "mean_intensity": cp.mean_intensity,
                "total_constrained_hours": cp.total_constrained_hours,
                "constrained_hours_pct": cp.constrained_hours_pct,
                "severity_score": cp.severity_score,
                "severity_tier": cp.severity_tier,
                "avg_marginal_cost": cp.avg_marginal_cost,
                "annual_cost": cp.annual_cost,
                "annotations": [
                    {"id": a.id, "annotation_type": a.annotation_type,
                     "title": a.title, "summary": a.summary,
                     "planned_solution": a.planned_solution,
                     "deferral_value_estimate": a.deferral_value_estimate,
                     "source_url": a.source_url, "confidence": a.confidence}
                    for a in annotations
                ],
            })

        # Best DER
        best_stack = (
            db.query(LocationValueStack)
            .filter_by(location_level="zone", location_id=resolution.zone_id)
            .order_by(LocationValueStack.total_value_per_kw_year.desc())
            .first()
        )
        if best_stack:
            dp = db.get(DERProfile, best_stack.der_profile_id)
            best_der = dp.der_type if dp else None
            total_value = best_stack.total_value_per_kw_year

    return {
        "lat": lat,
        "lon": lon,
        "iso_code": resolution.iso_code,
        "zone_code": resolution.zone_code,
        "substation_name": resolution.substation_name,
        "nearest_pnode_name": resolution.nearest_pnode_name,
        "feeder_id": resolution.feeder_id,
        "resolution_depth": resolution.resolution_depth or "none",
        "constraints": constraints,
        "best_der": best_der,
        "total_value_per_kw_year": total_value,
    }


@router.get("/zones/{iso_code}")
@cache_response("zones", ttl=3600)
async def list_zones(
    iso_code: str,
    request: Request = None,
    db: Session = Depends(get_db),
):
    """List zones with constraint summaries."""
    iso = db.query(ISO).filter(func.lower(ISO.iso_code) == iso_code.lower()).first()
    if not iso:
        raise HTTPException(status_code=404, detail=f"ISO '{iso_code}' not found")

    zones = db.query(Zone).filter_by(iso_id=iso.id).all()

    results = []
    for zone in zones:
        # Get primary constraint profile
        cp = (
            db.query(ConstraintProfile)
            .filter_by(location_level="zone", location_id=zone.id,
                       constraint_type="congestion")
            .order_by(ConstraintProfile.period_year.desc())
            .first()
        )

        # Count annotations
        annotation_count = 0
        best_der_type = None
        best_der_value = None

        if cp:
            annotation_count = (
                db.query(func.count(ConstraintAnnotation.id))
                .filter_by(constraint_profile_id=cp.id)
                .scalar()
            )

            # Best DER
            best = (
                db.query(ConstraintDERIntersection, DERProfile)
                .join(DERProfile, ConstraintDERIntersection.der_profile_id == DERProfile.id)
                .filter(ConstraintDERIntersection.constraint_profile_id == cp.id)
                .order_by(ConstraintDERIntersection.value_per_kw_year.desc())
                .first()
            )
            if best:
                best_der_type = best[1].der_type
                best_der_value = best[0].value_per_kw_year

        results.append(ZoneConstraintSummaryResponse(
            iso_code=iso.iso_code,
            zone_code=zone.zone_code,
            zone_name=zone.zone_name or zone.zone_code,
            centroid_lat=zone.centroid_lat,
            centroid_lon=zone.centroid_lon,
            primary_constraint_type=cp.constraint_type if cp else None,
            severity_score=cp.severity_score if cp else None,
            severity_tier=cp.severity_tier if cp else None,
            peak_month=cp.peak_month if cp else None,
            peak_hour=cp.peak_hour if cp else None,
            constrained_hours_pct=cp.constrained_hours_pct if cp else None,
            best_der_type=best_der_type,
            best_der_value_per_kw_year=best_der_value,
            annotation_count=annotation_count,
        ))

    return results


@router.get("/zones/{iso_code}/geometry")
@cache_response("zone-geometries", ttl=86400)
async def zone_geometries(
    iso_code: str,
    request: Request = None,
    db: Session = Depends(get_db),
):
    """Zone boundary GeoJSON (existing endpoint, preserved)."""
    iso = db.query(ISO).filter(func.lower(ISO.iso_code) == iso_code.lower()).first()
    if not iso:
        raise HTTPException(status_code=404, detail=f"ISO '{iso_code}' not found")

    zones = db.query(Zone).filter_by(iso_id=iso.id).all()
    features = []
    for z in zones:
        if z.boundary_geojson:
            features.append({
                "type": "Feature",
                "properties": {
                    "zone_code": z.zone_code,
                    "zone_name": z.zone_name,
                },
                "geometry": z.boundary_geojson,
            })
    return {"type": "FeatureCollection", "features": features}


@router.get("/zones/{iso_code}/{zone_code}/constraints")
@cache_response("zone-constraints", ttl=300)
async def zone_constraints(
    iso_code: str,
    zone_code: str,
    request: Request = None,
    db: Session = Depends(get_db),
):
    """All constraint profiles for a zone, with annotations inline."""
    iso = db.query(ISO).filter(func.lower(ISO.iso_code) == iso_code.lower()).first()
    if not iso:
        raise HTTPException(status_code=404, detail=f"ISO '{iso_code}' not found")

    zone = db.query(Zone).filter_by(iso_id=iso.id, zone_code=zone_code).first()
    if not zone:
        raise HTTPException(status_code=404, detail=f"Zone '{zone_code}' not found")

    profiles = (
        db.query(ConstraintProfile)
        .filter_by(location_level="zone", location_id=zone.id)
        .all()
    )

    profile_responses = []
    for cp in profiles:
        annotations = db.query(ConstraintAnnotation).filter_by(
            constraint_profile_id=cp.id).all()
        profile_responses.append(ConstraintProfileResponse(
            id=cp.id,
            location_level=cp.location_level,
            location_id=cp.location_id,
            location_name=zone.zone_name,
            constraint_type=cp.constraint_type,
            period_year=cp.period_year,
            profile_12x24=cp.profile_12x24,
            peak_intensity=cp.peak_intensity,
            peak_month=cp.peak_month,
            peak_hour=cp.peak_hour,
            mean_intensity=cp.mean_intensity,
            total_constrained_hours=cp.total_constrained_hours,
            constrained_hours_pct=cp.constrained_hours_pct,
            severity_score=cp.severity_score,
            severity_tier=cp.severity_tier,
            avg_marginal_cost=cp.avg_marginal_cost,
            annual_cost=cp.annual_cost,
            annotations=[AnnotationResponse.model_validate(a) for a in annotations],
        ))

    # Pnode hotspots
    from app.models.pnode import Pnode
    pnode_hotspots = (
        db.query(ConstraintProfile, Pnode)
        .join(Pnode, ConstraintProfile.location_id == Pnode.id)
        .filter(
            ConstraintProfile.location_level == "pnode",
            Pnode.zone_id == zone.id,
        )
        .order_by(ConstraintProfile.severity_score.desc())
        .limit(10)
        .all()
    )

    return {
        "profiles": profile_responses,
        "pnode_hotspots": [
            {
                "node_name": p.node_name,
                "severity_score": cp.severity_score,
                "severity_tier": cp.severity_tier,
                "lat": p.lat,
                "lon": p.lon,
            }
            for cp, p in pnode_hotspots
        ],
    }


@router.get("/zones/{iso_code}/{zone_code}/lmps")
@cache_response("zone-lmps", ttl=300)
async def zone_lmps(
    iso_code: str,
    zone_code: str,
    limit: int = Query(500, le=10000),
    offset: int = Query(0, ge=0),
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    request: Request = None,
    db: Session = Depends(get_db),
):
    """Raw hourly LMP data for a zone."""
    iso = db.query(ISO).filter(func.lower(ISO.iso_code) == iso_code.lower()).first()
    if not iso:
        raise HTTPException(status_code=404, detail=f"ISO '{iso_code}' not found")

    zone = db.query(Zone).filter_by(iso_id=iso.id, zone_code=zone_code).first()
    if not zone:
        raise HTTPException(status_code=404, detail=f"Zone '{zone_code}' not found")

    query = db.query(ZoneLMP).filter_by(zone_id=zone.id)
    if start_date:
        query = query.filter(ZoneLMP.timestamp_utc >= start_date)
    if end_date:
        query = query.filter(ZoneLMP.timestamp_utc <= end_date)

    lmps = (
        query
        .order_by(ZoneLMP.timestamp_utc.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    return [
        {
            "timestamp_utc": lmp.timestamp_utc.isoformat(),
            "lmp": lmp.lmp,
            "energy": lmp.energy,
            "congestion": lmp.congestion,
            "loss": lmp.loss,
        }
        for lmp in lmps
    ]


@router.get("/locations/{level}/{location_id}/profile")
@cache_response("location-profile", ttl=300)
async def location_profile(
    level: str,
    location_id: int,
    request: Request = None,
    db: Session = Depends(get_db),
):
    """Composite constraint profile for any location."""
    profiles = (
        db.query(ConstraintProfile)
        .filter_by(location_level=level, location_id=location_id)
        .all()
    )

    if not profiles:
        raise HTTPException(
            status_code=404,
            detail=f"No constraint profiles for {level}/{location_id}")

    from core.profile_utils import max_merge_12x24

    all_12x24s = [cp.profile_12x24 for cp in profiles]
    composite = max_merge_12x24(all_12x24s)

    profile_responses = []
    for cp in profiles:
        annotations = db.query(ConstraintAnnotation).filter_by(
            constraint_profile_id=cp.id).all()
        profile_responses.append(ConstraintProfileResponse(
            id=cp.id,
            location_level=cp.location_level,
            location_id=cp.location_id,
            constraint_type=cp.constraint_type,
            period_year=cp.period_year,
            profile_12x24=cp.profile_12x24,
            peak_intensity=cp.peak_intensity,
            peak_month=cp.peak_month,
            peak_hour=cp.peak_hour,
            mean_intensity=cp.mean_intensity,
            total_constrained_hours=cp.total_constrained_hours,
            constrained_hours_pct=cp.constrained_hours_pct,
            severity_score=cp.severity_score,
            severity_tier=cp.severity_tier,
            avg_marginal_cost=cp.avg_marginal_cost,
            annual_cost=cp.annual_cost,
            annotations=[AnnotationResponse.model_validate(a) for a in annotations],
        ))

    return {
        "location": {"level": level, "id": location_id},
        "profiles": profile_responses,
        "composite_12x24": composite,
    }


@router.get("/isos")
@cache_response("isos", ttl=3600)
async def list_isos(
    is_rto: Optional[bool] = None,
    request: Request = None,
    db: Session = Depends(get_db),
):
    """List ISOs and BAs."""
    query = db.query(ISO)
    if is_rto is not None:
        query = query.filter_by(is_rto=is_rto)
    isos = query.order_by(ISO.iso_code).all()

    return [
        {
            "id": iso.id,
            "iso_code": iso.iso_code,
            "iso_name": iso.iso_name,
            "timezone": iso.timezone,
            "is_rto": iso.is_rto,
            "ba_code": iso.ba_code,
            "ba_name": iso.ba_name,
            "region": iso.region,
            "latitude": iso.latitude,
            "longitude": iso.longitude,
        }
        for iso in isos
    ]
