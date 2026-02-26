"""API v1 routes for hierarchy browsing (substations, feeders, scores)."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import (
    ISO, Zone, Substation, Feeder, Pnode,
    PipelineRun, HierarchyScore,
)
from app.schemas.hierarchy_schemas import (
    SubstationResponse,
    SubstationDetailResponse,
    FeederResponse,
    HierarchyScoreResponse,
)

router = APIRouter(prefix="/api/v1")


@router.get("/isos/{iso_id}/substations", response_model=list[SubstationResponse])
def list_substations(
    iso_id: str,
    zone_code: Optional[str] = Query(None, description="Filter by zone code"),
    min_loading_pct: Optional[float] = Query(None, ge=0, description="Minimum peak loading %"),
    division: Optional[str] = Query(None, description="Filter by division"),
    limit: int = Query(default=200, le=5000),
    db: Session = Depends(get_db),
):
    """List substations for an ISO with optional filters."""
    iso = db.query(ISO).filter(ISO.iso_code == iso_id.lower()).first()
    if not iso:
        raise HTTPException(404, f"ISO '{iso_id}' not found")

    query = (
        db.query(Substation, Zone, Pnode)
        .outerjoin(Zone, Substation.zone_id == Zone.id)
        .outerjoin(Pnode, Substation.nearest_pnode_id == Pnode.id)
        .filter(Substation.iso_id == iso.id)
    )

    if zone_code:
        query = query.filter(Zone.zone_code == zone_code)
    if min_loading_pct is not None:
        query = query.filter(Substation.peak_loading_pct >= min_loading_pct)
    if division:
        query = query.filter(Substation.division == division)

    query = query.order_by(Substation.peak_loading_pct.desc().nullslast())
    results = query.limit(limit).all()

    return [
        SubstationResponse(
            id=sub.id,
            substation_name=sub.substation_name,
            bank_name=sub.bank_name,
            division=sub.division,
            facility_rating_mw=sub.facility_rating_mw,
            facility_loading_mw=sub.facility_loading_mw,
            peak_loading_pct=sub.peak_loading_pct,
            facility_type=sub.facility_type,
            lat=sub.lat,
            lon=sub.lon,
            zone_code=zone.zone_code if zone else None,
            nearest_pnode_name=pnode.node_name if pnode else None,
        )
        for sub, zone, pnode in results
    ]


@router.get("/substations/{substation_id}", response_model=SubstationDetailResponse)
def get_substation(
    substation_id: int,
    db: Session = Depends(get_db),
):
    """Get a single substation with full detail."""
    sub = db.query(Substation).get(substation_id)
    if not sub:
        raise HTTPException(404, f"Substation {substation_id} not found")

    zone = db.query(Zone).get(sub.zone_id) if sub.zone_id else None
    pnode = db.query(Pnode).get(sub.nearest_pnode_id) if sub.nearest_pnode_id else None
    feeder_count = db.query(func.count(Feeder.id)).filter(
        Feeder.substation_id == sub.id
    ).scalar()

    return SubstationDetailResponse(
        id=sub.id,
        substation_name=sub.substation_name,
        bank_name=sub.bank_name,
        division=sub.division,
        facility_rating_mw=sub.facility_rating_mw,
        facility_loading_mw=sub.facility_loading_mw,
        peak_loading_pct=sub.peak_loading_pct,
        facility_type=sub.facility_type,
        lat=sub.lat,
        lon=sub.lon,
        zone_id=sub.zone_id,
        zone_code=zone.zone_code if zone else None,
        nearest_pnode_id=sub.nearest_pnode_id,
        nearest_pnode_name=pnode.node_name if pnode else None,
        feeder_count=feeder_count or 0,
    )


@router.get("/substations/{substation_id}/feeders", response_model=list[FeederResponse])
def list_feeders(
    substation_id: int,
    db: Session = Depends(get_db),
):
    """List feeders for a substation."""
    sub = db.query(Substation).get(substation_id)
    if not sub:
        raise HTTPException(404, f"Substation {substation_id} not found")

    feeders = (
        db.query(Feeder)
        .filter(Feeder.substation_id == substation_id)
        .order_by(Feeder.peak_loading_pct.desc().nullslast())
        .all()
    )

    return [
        FeederResponse(
            id=f.id,
            substation_id=f.substation_id,
            feeder_id_external=f.feeder_id_external,
            capacity_mw=f.capacity_mw,
            peak_loading_mw=f.peak_loading_mw,
            peak_loading_pct=f.peak_loading_pct,
            voltage_kv=f.voltage_kv,
        )
        for f in feeders
    ]


@router.get("/hierarchy-scores", response_model=list[HierarchyScoreResponse])
def list_hierarchy_scores(
    level: Optional[str] = Query(None, description="Filter by level: zone, substation, feeder"),
    pipeline_run_id: Optional[int] = Query(None, description="Specific pipeline run"),
    iso_id: Optional[str] = Query(None, description="ISO code (uses latest run)"),
    min_combined_score: Optional[float] = Query(None, ge=0.0, le=1.0),
    constraint_tier: Optional[str] = Query(None, description="CRITICAL, ELEVATED, MODERATE, LOW"),
    limit: int = Query(default=200, le=5000),
    db: Session = Depends(get_db),
):
    """
    List hierarchy scores with filters.

    Either pipeline_run_id or iso_id must be provided. If iso_id is given,
    uses the latest completed pipeline run.
    """
    # Resolve pipeline run
    run_id = pipeline_run_id
    if not run_id and iso_id:
        iso = db.query(ISO).filter(ISO.iso_code == iso_id.lower()).first()
        if not iso:
            raise HTTPException(404, f"ISO '{iso_id}' not found")
        latest = (
            db.query(PipelineRun)
            .filter(PipelineRun.iso_id == iso.id, PipelineRun.status == "completed")
            .order_by(PipelineRun.completed_at.desc())
            .first()
        )
        if not latest:
            return []
        run_id = latest.id
    elif not run_id:
        raise HTTPException(400, "Provide either pipeline_run_id or iso_id")

    query = db.query(HierarchyScore).filter(
        HierarchyScore.pipeline_run_id == run_id,
    )

    if level:
        query = query.filter(HierarchyScore.level == level.lower())
    if min_combined_score is not None:
        query = query.filter(HierarchyScore.combined_score >= min_combined_score)
    if constraint_tier:
        query = query.filter(HierarchyScore.constraint_tier == constraint_tier.upper())

    query = query.order_by(HierarchyScore.combined_score.desc().nullslast())
    results = query.limit(limit).all()

    # Resolve entity names for display
    entity_names = _resolve_entity_names(db, results)

    return [
        HierarchyScoreResponse(
            id=hs.id,
            pipeline_run_id=hs.pipeline_run_id,
            level=hs.level,
            entity_id=hs.entity_id,
            congestion_score=hs.congestion_score,
            loading_score=hs.loading_score,
            combined_score=hs.combined_score,
            constraint_tier=hs.constraint_tier,
            entity_name=entity_names.get((hs.level, hs.entity_id)),
        )
        for hs in results
    ]


def _resolve_entity_names(
    db: Session, scores: list[HierarchyScore],
) -> dict[tuple[str, int], str]:
    """Resolve entity_id to human-readable names by level."""
    names = {}

    zone_ids = [s.entity_id for s in scores if s.level == "zone"]
    if zone_ids:
        zones = db.query(Zone).filter(Zone.id.in_(zone_ids)).all()
        for z in zones:
            names[("zone", z.id)] = z.zone_code

    sub_ids = [s.entity_id for s in scores if s.level == "substation"]
    if sub_ids:
        subs = db.query(Substation).filter(Substation.id.in_(sub_ids)).all()
        for s in subs:
            names[("substation", s.id)] = s.substation_name

    feeder_ids = [s.entity_id for s in scores if s.level == "feeder"]
    if feeder_ids:
        feeders = db.query(Feeder).filter(Feeder.id.in_(feeder_ids)).all()
        for f in feeders:
            names[("feeder", f.id)] = f.feeder_id_external or f"feeder-{f.id}"

    return names
