"""API v1 routes for hosting capacity data (utilities, feeders, summaries)."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.cache import cache_response

from app.api.v1.spatial import BBox, parse_bbox
from app.database import get_db
from app.models import (
    ISO, Utility, HostingCapacityRecord,
    HostingCapacitySummary, HCIngestionRun,
)
from app.schemas.hosting_capacity_schemas import (
    UtilityResponse,
    HostingCapacityResponse,
    HCSummaryResponse,
    HCIngestionRunResponse,
    HCNearbyResponse,
    HCProfileResponse,
)

router = APIRouter(prefix="/api/v1")


# ------------------------------------------------------------------
# Utilities
# ------------------------------------------------------------------

@router.get("/utilities", response_model=list[UtilityResponse])
@cache_response("hc-utilities", ttl=3600)
def list_utilities(request: Request = None, db: Session = Depends(get_db)):
    """List utilities that have hosting capacity data."""
    rows = (
        db.query(Utility, HostingCapacitySummary, ISO)
        .join(
            HostingCapacitySummary,
            Utility.id == HostingCapacitySummary.utility_id,
        )
        .outerjoin(ISO, Utility.iso_id == ISO.id)
        .order_by(Utility.utility_name)
        .all()
    )
    results = []
    for util, summary, iso in rows:
        results.append(UtilityResponse(
            utility_code=util.utility_code,
            utility_name=util.utility_name,
            parent_company=util.parent_company,
            iso_code=iso.iso_code if iso else None,
            states=util.states,
            data_source_type=util.data_source_type,
            last_ingested_at=util.last_ingested_at,
            total_feeders=summary.total_feeders if summary else None,
            total_hosting_capacity_mw=(
                summary.total_hosting_capacity_mw if summary else None
            ),
            total_remaining_capacity_mw=(
                summary.total_remaining_capacity_mw if summary else None
            ),
        ))
    return results


# ------------------------------------------------------------------
# Hosting Capacity Records
# ------------------------------------------------------------------

@router.get(
    "/utilities/{code}/hosting-capacity",
    response_model=list[HostingCapacityResponse],
)
@cache_response("hc-records", ttl=300)
def list_hosting_capacity(
    code: str,
    limit: int = Query(default=200, le=5000),
    offset: int = Query(default=0, ge=0),
    bbox: Optional[BBox] = Depends(parse_bbox),
    constraint: Optional[str] = Query(
        None, description="Filter by constraining_metric",
    ),
    min_capacity_mw: Optional[float] = Query(
        None, description="Minimum hosting_capacity_mw",
    ),
    request: Request = None,
    db: Session = Depends(get_db),
):
    """List hosting capacity records for a utility with optional filters.

    Supports bbox filtering: ?bbox=west,south,east,north
    """
    util = _get_utility(db, code)

    query = (
        db.query(HostingCapacityRecord)
        .filter(HostingCapacityRecord.utility_id == util.id)
    )

    if bbox:
        query = query.filter(bbox.filter_column(HostingCapacityRecord.geom))

    if constraint:
        query = query.filter(
            HostingCapacityRecord.constraining_metric == constraint,
        )

    if min_capacity_mw is not None:
        query = query.filter(
            HostingCapacityRecord.hosting_capacity_mw >= min_capacity_mw,
        )

    records = query.offset(offset).limit(limit).all()

    return [
        HostingCapacityResponse(
            id=r.id,
            utility_code=util.utility_code,
            feeder_id_external=r.feeder_id_external,
            feeder_name=r.feeder_name,
            substation_name=r.substation_name,
            hosting_capacity_mw=r.hosting_capacity_mw,
            hosting_capacity_min_mw=r.hosting_capacity_min_mw,
            hosting_capacity_max_mw=r.hosting_capacity_max_mw,
            remaining_capacity_mw=r.remaining_capacity_mw,
            installed_dg_mw=r.installed_dg_mw,
            queued_dg_mw=r.queued_dg_mw,
            constraining_metric=r.constraining_metric,
            voltage_kv=r.voltage_kv,
            phase_config=r.phase_config,
            centroid_lat=r.centroid_lat,
            centroid_lon=r.centroid_lon,
        )
        for r in records
    ]


# ------------------------------------------------------------------
# GeoJSON export
# ------------------------------------------------------------------

@router.get("/utilities/{code}/hosting-capacity/geojson")
@cache_response("hc-geojson", ttl=300)
def hosting_capacity_geojson(
    code: str,
    limit: int = Query(default=5000, le=50000),
    bbox: Optional[BBox] = Depends(parse_bbox),
    constraint: Optional[str] = Query(None),
    request: Request = None,
    db: Session = Depends(get_db),
):
    """Export hosting capacity records as a GeoJSON FeatureCollection.

    Supports bbox filtering: ?bbox=west,south,east,north
    """
    util = _get_utility(db, code)

    query = (
        db.query(HostingCapacityRecord)
        .filter(HostingCapacityRecord.utility_id == util.id)
        .filter(HostingCapacityRecord.centroid_lat.isnot(None))
    )

    if bbox:
        query = query.filter(bbox.filter_column(HostingCapacityRecord.geom))

    if constraint:
        query = query.filter(
            HostingCapacityRecord.constraining_metric == constraint,
        )

    records = query.limit(limit).all()

    features = []
    for r in records:
        features.append({
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [r.centroid_lon, r.centroid_lat],
            },
            "properties": {
                "id": r.id,
                "feeder_id_external": r.feeder_id_external,
                "feeder_name": r.feeder_name,
                "hosting_capacity_mw": r.hosting_capacity_mw,
                "remaining_capacity_mw": r.remaining_capacity_mw,
                "installed_dg_mw": r.installed_dg_mw,
                "constraining_metric": r.constraining_metric,
                "voltage_kv": r.voltage_kv,
            },
        })

    return {"type": "FeatureCollection", "features": features}


# ------------------------------------------------------------------
# Summary
# ------------------------------------------------------------------

@router.get(
    "/utilities/{code}/hosting-capacity/summary",
    response_model=HCSummaryResponse,
)
@cache_response("hc-summary", ttl=3600)
def hosting_capacity_summary(
    code: str,
    request: Request = None,
    db: Session = Depends(get_db),
):
    """Get aggregated hosting capacity summary for a utility."""
    util = _get_utility(db, code)

    summary = (
        db.query(HostingCapacitySummary)
        .filter(HostingCapacitySummary.utility_id == util.id)
        .first()
    )
    if not summary:
        raise HTTPException(404, f"No summary for utility '{code}'")

    return HCSummaryResponse(
        utility_code=util.utility_code,
        utility_name=util.utility_name,
        total_feeders=summary.total_feeders,
        total_hosting_capacity_mw=summary.total_hosting_capacity_mw,
        total_installed_dg_mw=summary.total_installed_dg_mw,
        total_remaining_capacity_mw=summary.total_remaining_capacity_mw,
        avg_utilization_pct=summary.avg_utilization_pct,
        constrained_feeders_count=summary.constrained_feeders_count,
        constraint_breakdown=summary.constraint_breakdown,
        computed_at=summary.computed_at,
    )


# ------------------------------------------------------------------
# Ingestion runs
# ------------------------------------------------------------------

@router.get(
    "/utilities/{code}/ingestion-runs",
    response_model=list[HCIngestionRunResponse],
)
@cache_response("hc-ingestion-runs", ttl=300)
def list_ingestion_runs(
    code: str,
    limit: int = Query(default=10, le=100),
    request: Request = None,
    db: Session = Depends(get_db),
):
    """List recent ingestion runs for a utility."""
    util = _get_utility(db, code)

    runs = (
        db.query(HCIngestionRun)
        .filter(HCIngestionRun.utility_id == util.id)
        .order_by(HCIngestionRun.started_at.desc())
        .limit(limit)
        .all()
    )

    return [
        HCIngestionRunResponse(
            id=r.id,
            utility_code=util.utility_code,
            started_at=r.started_at,
            completed_at=r.completed_at,
            status=r.status,
            records_fetched=r.records_fetched,
            records_written=r.records_written,
            error_message=r.error_message,
        )
        for r in runs
    ]


# ------------------------------------------------------------------
# 12x24 HC Availability Profile
# ------------------------------------------------------------------

@router.get(
    "/utilities/{code}/hosting-capacity/profile-12x24",
    response_model=HCProfileResponse,
)
@cache_response("hc-profile", ttl=3600)
def hosting_capacity_profile_12x24(
    code: str,
    year: int = Query(default=2024, ge=2020, le=2030),
    request: Request = None,
    db: Session = Depends(get_db),
):
    """Estimated 12x24 HC availability index based on ISO load shape.

    Computes a normalized load profile from EIA-930 hourly demand data for
    the utility's parent ISO, inverts it, and returns an availability index
    (0-100) for each (month, hour). High values = low load = more HC headroom.
    """
    import pandas as pd
    from app.models.congestion import BAHourlyData
    from sqlalchemy import extract

    util = _get_utility(db, code)

    if not util.iso_id:
        raise HTTPException(
            404,
            f"Utility '{code}' has no associated ISO; cannot compute load profile",
        )

    iso = db.query(ISO).filter(ISO.id == util.iso_id).first()
    if not iso:
        raise HTTPException(404, f"ISO not found for utility '{code}'")

    # Query hourly demand: first try the ISO directly, then aggregate child BAs
    hourly_q = (
        db.query(
            BAHourlyData.timestamp_utc,
            BAHourlyData.demand_mw,
        )
        .filter(
            BAHourlyData.ba_id == iso.id,
            extract("year", BAHourlyData.timestamp_utc) == year,
            BAHourlyData.demand_mw.isnot(None),
        )
    )
    rows = hourly_q.all()

    # If no rows for the ISO itself, try aggregating child BAs
    if not rows:
        from sqlalchemy import func

        child_ids = [c.id for c in iso.child_bas] if iso.child_bas else []
        if not child_ids:
            raise HTTPException(
                404,
                f"No hourly demand data for ISO '{iso.iso_code}' or its child BAs in {year}",
            )

        rows = (
            db.query(
                BAHourlyData.timestamp_utc,
                func.sum(BAHourlyData.demand_mw).label("demand_mw"),
            )
            .filter(
                BAHourlyData.ba_id.in_(child_ids),
                extract("year", BAHourlyData.timestamp_utc) == year,
                BAHourlyData.demand_mw.isnot(None),
            )
            .group_by(BAHourlyData.timestamp_utc)
            .all()
        )

    if not rows:
        raise HTTPException(
            404,
            f"No hourly demand data available for ISO '{iso.iso_code}' in {year}",
        )

    # Build DataFrame and compute 12x24 profile
    df = pd.DataFrame(rows, columns=["timestamp_utc", "demand_mw"])

    # Convert UTC to ISO's local timezone for correct month/hour grouping
    local_tz = iso.timezone if iso.timezone and iso.timezone != "UTC" else "US/Eastern"
    df["timestamp_utc"] = pd.to_datetime(df["timestamp_utc"], utc=True)
    df["local_time"] = df["timestamp_utc"].dt.tz_convert(local_tz)
    df["month"] = df["local_time"].dt.month
    df["hour"] = df["local_time"].dt.hour

    pivot = df.groupby(["month", "hour"])["demand_mw"].mean().reset_index()
    peak_demand = pivot["demand_mw"].max()

    if peak_demand <= 0:
        raise HTTPException(500, "Peak demand is zero; cannot normalize")

    pivot["normalized_load"] = pivot["demand_mw"] / peak_demand
    pivot["availability"] = (1 - pivot["normalized_load"]) * 100

    # Build the 12x24 dict: month "1"-"12" → list of 24 hourly values
    profile: dict[str, list[float]] = {}
    for month in range(1, 13):
        month_data = pivot[pivot["month"] == month].sort_values("hour")
        if len(month_data) == 0:
            profile[str(month)] = [0.0] * 24
        else:
            profile[str(month)] = [round(v, 1) for v in month_data["availability"].tolist()]

    # Find peak availability (lowest load)
    peak_row = pivot.loc[pivot["availability"].idxmax()]

    return HCProfileResponse(
        utility_code=util.utility_code,
        utility_name=util.utility_name,
        iso_code=iso.iso_code,
        year=year,
        profile_12x24=profile,
        peak_month=int(peak_row["month"]),
        peak_hour=int(peak_row["hour"]),
    )


# ------------------------------------------------------------------
# Nearby search (cross-utility)
# ------------------------------------------------------------------

@router.get(
    "/hosting-capacity/nearby",
    response_model=list[HCNearbyResponse],
)
def hosting_capacity_nearby(
    lat: float = Query(..., description="Latitude"),
    lon: float = Query(..., description="Longitude"),
    radius_km: float = Query(default=10, le=100, description="Search radius in km"),
    limit: int = Query(default=50, le=500),
    db: Session = Depends(get_db),
):
    """Find hosting capacity records near a point, across all utilities.

    Uses PostGIS ST_DWithin for efficient spatial search with GiST index,
    then ST_Distance for exact distance computation and sorting.
    """
    from geoalchemy2.functions import ST_DWithin, ST_Distance, ST_MakePoint, ST_SetSRID
    from geoalchemy2.types import Geography
    from sqlalchemy import cast, func

    # Build the search point
    search_point = ST_SetSRID(ST_MakePoint(lon, lat), 4326)

    # ST_DWithin on geography type uses meters
    radius_m = radius_km * 1000

    # Distance expression (meters, using geography cast for accuracy)
    dist_expr = ST_Distance(
        cast(HostingCapacityRecord.geom, Geography),
        cast(search_point, Geography),
    )

    results = (
        db.query(
            HostingCapacityRecord,
            Utility,
            (dist_expr / 1000.0).label("distance_km"),
        )
        .join(Utility, HostingCapacityRecord.utility_id == Utility.id)
        .filter(
            HostingCapacityRecord.geom.isnot(None),
            ST_DWithin(
                cast(HostingCapacityRecord.geom, Geography),
                cast(search_point, Geography),
                radius_m,
            ),
        )
        .order_by(dist_expr)
        .limit(limit)
        .all()
    )

    return [
        HCNearbyResponse(
            id=r.id,
            utility_code=u.utility_code,
            feeder_id_external=r.feeder_id_external,
            feeder_name=r.feeder_name,
            hosting_capacity_mw=r.hosting_capacity_mw,
            remaining_capacity_mw=r.remaining_capacity_mw,
            constraining_metric=r.constraining_metric,
            centroid_lat=r.centroid_lat,
            centroid_lon=r.centroid_lon,
            distance_km=round(dist, 2),
        )
        for r, u, dist in results
    ]


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _get_utility(db: Session, code: str) -> Utility:
    """Look up utility by code or raise 404."""
    util = (
        db.query(Utility)
        .filter(Utility.utility_code == code.lower())
        .first()
    )
    if not util:
        raise HTTPException(404, f"Utility '{code}' not found")
    return util



