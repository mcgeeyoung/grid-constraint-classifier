"""API v1 route handlers."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth import require_api_key
from app.database import get_db
from app.models import (
    ISO, Zone, ZoneLMP, PipelineRun, ZoneClassification,
    Pnode, PnodeScore, DataCenter, DERRecommendation,
    Substation, DERLocation, DERValuation,
)
from app.schemas.responses import (
    ISOResponse, ZoneResponse, ZoneClassificationResponse,
    PnodeScoreResponse, ZoneLMPResponse, DataCenterResponse,
    DERRecommendationResponse, PipelineRunResponse, OverviewResponse,
    ValueSummaryResponse, TopZone,
)

limiter = Limiter(key_func=get_remote_address)

router = APIRouter(prefix="/api/v1")


@router.get("/isos", response_model=list[ISOResponse])
def list_isos(db: Session = Depends(get_db)):
    """List all ISOs."""
    isos = db.query(ISO).order_by(ISO.iso_code).all()
    return isos


@router.get("/isos/{iso_id}/zones", response_model=list[ZoneResponse])
def list_zones(iso_id: str, db: Session = Depends(get_db)):
    """List zones for an ISO."""
    iso = db.query(ISO).filter(ISO.iso_code == iso_id.lower()).first()
    if not iso:
        raise HTTPException(404, f"ISO '{iso_id}' not found")
    zones = db.query(Zone).filter(Zone.iso_id == iso.id).order_by(Zone.zone_code).all()
    return zones


@router.get("/isos/{iso_id}/classifications", response_model=list[ZoneClassificationResponse])
def get_classifications(iso_id: str, db: Session = Depends(get_db)):
    """Get latest zone classifications for an ISO."""
    iso = db.query(ISO).filter(ISO.iso_code == iso_id.lower()).first()
    if not iso:
        raise HTTPException(404, f"ISO '{iso_id}' not found")

    # Get the latest completed pipeline run
    latest_run = (
        db.query(PipelineRun)
        .filter(PipelineRun.iso_id == iso.id, PipelineRun.status == "completed")
        .order_by(PipelineRun.completed_at.desc())
        .first()
    )
    if not latest_run:
        return []

    results = (
        db.query(ZoneClassification, Zone)
        .join(Zone, ZoneClassification.zone_id == Zone.id)
        .filter(ZoneClassification.pipeline_run_id == latest_run.id)
        .order_by(ZoneClassification.transmission_score.desc())
        .all()
    )

    return [
        ZoneClassificationResponse(
            zone_code=zone.zone_code,
            zone_name=zone.zone_name,
            classification=cls.classification,
            transmission_score=cls.transmission_score,
            generation_score=cls.generation_score,
            avg_abs_congestion=cls.avg_abs_congestion,
            max_congestion=cls.max_congestion,
            congested_hours_pct=cls.congested_hours_pct,
        )
        for cls, zone in results
    ]


@router.get("/isos/{iso_id}/zones/{zone_code}/pnodes", response_model=list[PnodeScoreResponse])
def get_pnode_scores(iso_id: str, zone_code: str, db: Session = Depends(get_db)):
    """Get pnode severity scores for a zone."""
    iso = db.query(ISO).filter(ISO.iso_code == iso_id.lower()).first()
    if not iso:
        raise HTTPException(404, f"ISO '{iso_id}' not found")

    zone = db.query(Zone).filter(Zone.iso_id == iso.id, Zone.zone_code == zone_code).first()
    if not zone:
        raise HTTPException(404, f"Zone '{zone_code}' not found in {iso_id}")

    latest_run = (
        db.query(PipelineRun)
        .filter(PipelineRun.iso_id == iso.id, PipelineRun.status == "completed")
        .order_by(PipelineRun.completed_at.desc())
        .first()
    )
    if not latest_run:
        return []

    results = (
        db.query(PnodeScore, Pnode)
        .join(Pnode, PnodeScore.pnode_id == Pnode.id)
        .filter(
            PnodeScore.pipeline_run_id == latest_run.id,
            Pnode.zone_id == zone.id,
        )
        .order_by(PnodeScore.severity_score.desc())
        .all()
    )

    return [
        PnodeScoreResponse(
            node_id_external=pnode.node_id_external,
            node_name=pnode.node_name,
            severity_score=score.severity_score,
            tier=score.tier,
            avg_congestion=score.avg_congestion,
            max_congestion=score.max_congestion,
            congested_hours_pct=score.congested_hours_pct,
            lat=pnode.lat,
            lon=pnode.lon,
        )
        for score, pnode in results
    ]


@router.get("/isos/{iso_id}/zones/{zone_code}/lmps", response_model=list[ZoneLMPResponse])
def get_zone_lmps(
    iso_id: str,
    zone_code: str,
    limit: int = Query(default=500, le=10000),
    month: Optional[int] = Query(default=None, ge=1, le=12),
    db: Session = Depends(get_db),
):
    """Get zone LMP time series (paginated)."""
    iso = db.query(ISO).filter(ISO.iso_code == iso_id.lower()).first()
    if not iso:
        raise HTTPException(404, f"ISO '{iso_id}' not found")

    zone = db.query(Zone).filter(Zone.iso_id == iso.id, Zone.zone_code == zone_code).first()
    if not zone:
        raise HTTPException(404, f"Zone '{zone_code}' not found in {iso_id}")

    query = (
        db.query(ZoneLMP)
        .filter(ZoneLMP.iso_id == iso.id, ZoneLMP.zone_id == zone.id)
    )

    if month is not None:
        query = query.filter(ZoneLMP.month == month)

    lmps = query.order_by(ZoneLMP.timestamp_utc.desc()).limit(limit).all()
    return lmps


@router.get("/data-centers", response_model=list[DataCenterResponse])
def list_data_centers(
    iso_id: Optional[str] = None,
    zone_code: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = Query(default=100, le=5000),
    db: Session = Depends(get_db),
):
    """List data centers, filterable by ISO, zone, status."""
    query = db.query(DataCenter, ISO, Zone).join(ISO).outerjoin(Zone)

    if iso_id:
        query = query.filter(ISO.iso_code == iso_id.lower())
    if zone_code:
        query = query.filter(Zone.zone_code == zone_code)
    if status:
        query = query.filter(DataCenter.status == status.lower())

    results = query.limit(limit).all()

    return [
        DataCenterResponse(
            external_slug=dc.external_slug,
            facility_name=dc.facility_name,
            status=dc.status,
            capacity_mw=dc.capacity_mw,
            lat=dc.lat,
            lon=dc.lon,
            state_code=dc.state_code,
            county=dc.county,
            operator=dc.operator,
            iso_code=iso.iso_code,
            zone_code=zone.zone_code if zone else None,
        )
        for dc, iso, zone in results
    ]


@router.get("/isos/{iso_id}/recommendations", response_model=list[DERRecommendationResponse])
def get_recommendations(iso_id: str, db: Session = Depends(get_db)):
    """Get DER recommendations for an ISO."""
    iso = db.query(ISO).filter(ISO.iso_code == iso_id.lower()).first()
    if not iso:
        raise HTTPException(404, f"ISO '{iso_id}' not found")

    latest_run = (
        db.query(PipelineRun)
        .filter(PipelineRun.iso_id == iso.id, PipelineRun.status == "completed")
        .order_by(PipelineRun.completed_at.desc())
        .first()
    )
    if not latest_run:
        return []

    results = (
        db.query(DERRecommendation, Zone)
        .join(Zone)
        .filter(DERRecommendation.pipeline_run_id == latest_run.id)
        .order_by(Zone.zone_code)
        .all()
    )

    return [
        DERRecommendationResponse(
            zone_code=zone.zone_code,
            classification=rec.classification,
            rationale=rec.rationale,
            congestion_value=rec.congestion_value,
            primary_rec=rec.primary_rec,
            secondary_rec=rec.secondary_rec,
            tertiary_rec=rec.tertiary_rec,
        )
        for rec, zone in results
    ]


@router.get("/pipeline/runs", response_model=list[PipelineRunResponse])
def list_pipeline_runs(
    iso_id: Optional[str] = None,
    limit: int = Query(default=20, le=100),
    db: Session = Depends(get_db),
):
    """List pipeline runs."""
    query = db.query(PipelineRun, ISO).join(ISO)

    if iso_id:
        query = query.filter(ISO.iso_code == iso_id.lower())

    results = query.order_by(PipelineRun.started_at.desc()).limit(limit).all()

    return [
        PipelineRunResponse(
            id=run.id,
            iso_code=iso.iso_code,
            year=run.year,
            started_at=run.started_at,
            completed_at=run.completed_at,
            status=run.status,
            zone_lmp_rows=run.zone_lmp_rows,
            error_message=run.error_message,
        )
        for run, iso in results
    ]


@router.get("/overview", response_model=list[OverviewResponse])
def get_overview(db: Session = Depends(get_db)):
    """Cross-ISO summary."""
    isos = db.query(ISO).order_by(ISO.iso_code).all()
    result = []

    for iso in isos:
        zones_count = db.query(Zone).filter(Zone.iso_id == iso.id).count()

        latest_run = (
            db.query(PipelineRun)
            .filter(PipelineRun.iso_id == iso.id, PipelineRun.status == "completed")
            .order_by(PipelineRun.completed_at.desc())
            .first()
        )

        overview = OverviewResponse(
            iso_code=iso.iso_code,
            iso_name=iso.iso_name,
            zones_count=zones_count,
        )

        if latest_run:
            overview.latest_run_year = latest_run.year
            overview.latest_run_status = latest_run.status

            cls_counts = (
                db.query(ZoneClassification.classification, func.count())
                .filter(ZoneClassification.pipeline_run_id == latest_run.id)
                .group_by(ZoneClassification.classification)
                .all()
            )
            for cls, count in cls_counts:
                if cls == "transmission":
                    overview.transmission_constrained = count
                elif cls == "generation":
                    overview.generation_constrained = count
                elif cls == "both":
                    overview.both_constrained = count
                elif cls == "unconstrained":
                    overview.unconstrained = count

        result.append(overview)

    return result


@router.get(
    "/isos/{iso_id}/value-summary",
    response_model=ValueSummaryResponse,
    dependencies=[Depends(require_api_key)],
)
@limiter.limit("30/minute")
def get_value_summary(
    iso_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    """Aggregated value summary for an ISO.

    Requires X-API-Key header. Rate-limited to 30 requests per minute.
    """
    iso = db.query(ISO).filter(ISO.iso_code == iso_id.lower()).first()
    if not iso:
        raise HTTPException(404, f"ISO '{iso_id}' not found")

    # Zone counts
    total_zones = db.query(Zone).filter(Zone.iso_id == iso.id).count()

    latest_run = (
        db.query(PipelineRun)
        .filter(PipelineRun.iso_id == iso.id, PipelineRun.status == "completed")
        .order_by(PipelineRun.completed_at.desc())
        .first()
    )

    constrained_zones = 0
    if latest_run:
        constrained_zones = (
            db.query(ZoneClassification)
            .filter(
                ZoneClassification.pipeline_run_id == latest_run.id,
                ZoneClassification.classification != "unconstrained",
            )
            .count()
        )

    # Substation counts
    total_substations = (
        db.query(Substation).filter(Substation.iso_id == iso.id).count()
    )
    overloaded_substations = (
        db.query(Substation)
        .filter(
            Substation.iso_id == iso.id,
            Substation.peak_loading_pct >= 80.0,
        )
        .count()
    )

    # DER location + valuation aggregates
    total_der_locations = (
        db.query(DERLocation).filter(DERLocation.iso_id == iso.id).count()
    )

    val_agg = (
        db.query(
            func.coalesce(func.sum(DERValuation.total_constraint_relief_value), 0.0),
            func.coalesce(func.avg(
                DERValuation.total_constraint_relief_value
                / (DERLocation.capacity_mw * 1000)
            ), 0.0),
        )
        .join(DERLocation, DERValuation.der_location_id == DERLocation.id)
        .filter(DERLocation.iso_id == iso.id)
        .first()
    )
    total_portfolio_value = float(val_agg[0]) if val_agg else 0.0
    avg_value_per_kw_year = float(val_agg[1]) if val_agg else 0.0

    # Tier distribution
    tier_rows = (
        db.query(DERValuation.value_tier, func.count())
        .join(DERLocation, DERValuation.der_location_id == DERLocation.id)
        .filter(
            DERLocation.iso_id == iso.id,
            DERValuation.value_tier.isnot(None),
        )
        .group_by(DERValuation.value_tier)
        .all()
    )
    tier_distribution = {tier: count for tier, count in tier_rows}

    # Top 5 zones by average constraint value
    top_zone_rows = (
        db.query(
            Zone.zone_code,
            Zone.zone_name,
            func.avg(DERValuation.total_constraint_relief_value).label("avg_val"),
        )
        .join(DERLocation, DERLocation.zone_id == Zone.id)
        .join(DERValuation, DERValuation.der_location_id == DERLocation.id)
        .filter(Zone.iso_id == iso.id)
        .group_by(Zone.zone_code, Zone.zone_name)
        .order_by(func.avg(DERValuation.total_constraint_relief_value).desc())
        .limit(5)
        .all()
    )
    top_zones = [
        TopZone(
            zone_code=row.zone_code,
            zone_name=row.zone_name,
            avg_constraint_value=float(row.avg_val) if row.avg_val else 0.0,
        )
        for row in top_zone_rows
    ]

    return ValueSummaryResponse(
        iso_code=iso.iso_code,
        iso_name=iso.iso_name,
        total_zones=total_zones,
        constrained_zones=constrained_zones,
        total_substations=total_substations,
        overloaded_substations=overloaded_substations,
        total_der_locations=total_der_locations,
        total_portfolio_value=total_portfolio_value,
        avg_value_per_kw_year=avg_value_per_kw_year,
        tier_distribution=tier_distribution,
        top_zones=top_zones,
    )
