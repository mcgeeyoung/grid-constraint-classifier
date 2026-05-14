"""Enrichment routes: supporting context data.

Hosting capacity, interconnection queue, utility filings, and utility registry.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.cache import cache_response
from app.database import get_db
from app.models.utility import Utility
from app.models.filing import Filing
from app.models.hosting_capacity import HostingCapacityRecord
from app.models.interconnection_queue import InterconnectionQueue

router = APIRouter(prefix="/api/enrichment", tags=["enrichment"])


@router.get("/hosting-capacity")
def nearby_hosting_capacity(
    lat: float = Query(...),
    lon: float = Query(...),
    radius_km: float = Query(10.0, le=100),
    db: Session = Depends(get_db),
):
    """Feeders with hosting capacity near a lat/lon."""
    # Use PostGIS spatial query if available, otherwise fallback to bounding box
    deg_offset = radius_km / 111.0
    records = (
        db.query(HostingCapacityRecord, Utility)
        .join(Utility, HostingCapacityRecord.utility_id == Utility.id)
        .filter(
            HostingCapacityRecord.centroid_lat.isnot(None),
            HostingCapacityRecord.centroid_lat.between(lat - deg_offset, lat + deg_offset),
            HostingCapacityRecord.centroid_lon.between(lon - deg_offset, lon + deg_offset),
        )
        .limit(50)
        .all()
    )
    results = []
    for r, u in records:
        raw = r.raw_attributes or {}
        results.append({
            "feeder_name": r.feeder_name,
            "substation_name": r.substation_name,
            "hosting_capacity_mw": r.hosting_capacity_mw,
            "remaining_capacity_mw": r.remaining_capacity_mw,
            "constraining_metric": r.constraining_metric,
            "capacity_status": raw.get("expectedcapacity") or raw.get("Capacity_Status"),
            "has_ica": raw.get("loadica"),
            "utility_code": u.utility_code,
            "lat": r.centroid_lat,
            "lon": r.centroid_lon,
        })
    return results


@router.get("/interconnection-queue")
def nearby_interconnection(
    lat: float = Query(...),
    lon: float = Query(...),
    radius_km: float = Query(50.0, le=200),
    db: Session = Depends(get_db),
):
    """Interconnection queue projects near a lat/lon."""
    deg_offset = radius_km / 111.0
    projects = (
        db.query(InterconnectionQueue)
        .filter(
            InterconnectionQueue.latitude.isnot(None),
            InterconnectionQueue.latitude.between(lat - deg_offset, lat + deg_offset),
            InterconnectionQueue.longitude.between(lon - deg_offset, lon + deg_offset),
        )
        .limit(50)
        .all()
    )

    return [
        {
            "project_name": p.project_name,
            "generation_type": p.generation_type,
            "capacity_mw": p.capacity_mw,
            "queue_status": p.queue_status,
            "proposed_online_date": str(p.proposed_online_date) if p.proposed_online_date else None,
            "lat": p.latitude,
            "lon": p.longitude,
        }
        for p in projects
    ]


@router.get("/interconnection-queue/all")
@cache_response("iq-all", ttl=3600)
def all_interconnection_queue(
    request: Request = None,
    db: Session = Depends(get_db),
):
    """All interconnection queue projects with coordinates (for map display)."""
    projects = (
        db.query(InterconnectionQueue)
        .filter(InterconnectionQueue.latitude.isnot(None))
        .limit(500)
        .all()
    )
    return [
        {
            "project_name": p.project_name,
            "generation_type": p.generation_type,
            "capacity_mw": p.capacity_mw,
            "queue_status": p.queue_status,
            "proposed_online_date": str(p.proposed_online_date) if p.proposed_online_date else None,
            "lat": p.latitude,
            "lon": p.longitude,
        }
        for p in projects
    ]


@router.get("/filings/{utility_code}")
def utility_filings(
    utility_code: str,
    filing_type: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Full filing history for a utility."""
    from sqlalchemy import or_
    # Match by EIA ID (if numeric), utility_code, or name
    # Escape SQL LIKE wildcards to prevent unintended pattern matching
    safe_name = utility_code.replace("%", r"\%").replace("_", r"\_")
    conditions = [
        Utility.utility_code == utility_code,
        Utility.utility_name.ilike(f"%{safe_name}%", escape="\\"),
    ]
    try:
        conditions.append(Utility.eia_id == int(utility_code))
    except ValueError:
        pass
    utility = db.query(Utility).filter(or_(*conditions)).first()
    if not utility:
        raise HTTPException(status_code=404, detail=f"Utility '{utility_code}' not found")

    query = db.query(Filing).filter_by(utility_id=utility.id)
    if filing_type:
        query = query.filter_by(filing_type=filing_type)

    filings = query.order_by(Filing.filed_date.desc()).all()

    return [
        {
            "id": f.id,
            "docket_number": f.docket_number,
            "filing_type": f.filing_type,
            "title": f.title,
            "filed_date": str(f.filed_date) if f.filed_date else None,
            "source_url": f.source_url,
            "summary": f.summary,
        }
        for f in filings
    ]


@router.get("/utilities")
@cache_response("utilities", ttl=3600)
def list_utilities(
    state: Optional[str] = None,
    iso_code: Optional[str] = None,
    request: Request = None,
    db: Session = Depends(get_db),
):
    """Utility registry."""
    query = db.query(Utility)
    if state:
        query = query.filter_by(state=state.upper())

    utilities = query.order_by(Utility.utility_name).limit(500).all()

    return [
        {
            "id": u.id,
            "utility_name": u.utility_name,
            "eia_id": u.eia_id,
            "state": u.state,
            "utility_type": u.utility_type,
        }
        for u in utilities
    ]
