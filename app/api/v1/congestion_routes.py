"""API v1 routes for import congestion data."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.cache import cache_response

from app.database import get_db
from app.models.congestion import (
    BalancingAuthority,
    BAHourlyData,
    CongestionScore,
)
from app.schemas.congestion_schemas import (
    BAResponse,
    CongestionScoreResponse,
    DurationCurveResponse,
    HourlyDataResponse,
)

router = APIRouter(prefix="/api/v1/congestion")


@router.get("/bas", response_model=list[BAResponse])
@cache_response("congestion-bas", ttl=3600)
def list_bas(
    rto_only: bool = Query(False, description="Only return RTOs"),
    request: Request = None,
    db: Session = Depends(get_db),
):
    """List all balancing authorities with metadata."""
    query = db.query(BalancingAuthority)
    if rto_only:
        query = query.filter(BalancingAuthority.is_rto.is_(True))
    return query.order_by(BalancingAuthority.ba_code).all()


@router.get("/scores", response_model=list[CongestionScoreResponse])
@cache_response("congestion-scores", ttl=3600)
def list_scores(
    period_type: str = Query("year", description="'month' or 'year'"),
    year: Optional[int] = Query(None, description="Filter by year"),
    request: Request = None,
    db: Session = Depends(get_db),
):
    """Get ranked congestion scores for all BAs."""
    query = (
        db.query(CongestionScore, BalancingAuthority)
        .join(BalancingAuthority, CongestionScore.ba_id == BalancingAuthority.id)
        .filter(CongestionScore.period_type == period_type)
    )
    if year:
        query = query.filter(
            CongestionScore.period_start >= f"{year}-01-01",
            CongestionScore.period_start < f"{year + 1}-01-01",
        )

    rows = query.order_by(CongestionScore.hours_above_80.desc().nullslast()).all()

    results = []
    for score, ba in rows:
        results.append(CongestionScoreResponse(
            ba_code=ba.ba_code,
            ba_name=ba.ba_name,
            region=ba.region,
            period_start=score.period_start,
            period_end=score.period_end,
            period_type=score.period_type,
            hours_total=score.hours_total,
            hours_importing=score.hours_importing,
            pct_hours_importing=score.pct_hours_importing,
            hours_above_80=score.hours_above_80,
            hours_above_90=score.hours_above_90,
            hours_above_95=score.hours_above_95,
            avg_import_pct_of_load=score.avg_import_pct_of_load,
            max_import_pct_of_load=score.max_import_pct_of_load,
            avg_congestion_premium=score.avg_congestion_premium,
            congestion_opportunity_score=score.congestion_opportunity_score,
            transfer_limit_used=score.transfer_limit_used,
            lmp_coverage=score.lmp_coverage,
            data_quality_flag=score.data_quality_flag,
        ))
    return results


@router.get("/scores/{ba_code}", response_model=list[CongestionScoreResponse])
@cache_response("congestion-ba-scores", ttl=3600)
def get_ba_scores(
    ba_code: str,
    period_type: str = Query("month", description="'month' or 'year'"),
    year: Optional[int] = Query(None, description="Filter by year"),
    request: Request = None,
    db: Session = Depends(get_db),
):
    """Get congestion scores for a specific BA."""
    ba = db.query(BalancingAuthority).filter_by(ba_code=ba_code.upper()).first()
    if not ba:
        raise HTTPException(status_code=404, detail=f"BA '{ba_code}' not found")

    query = (
        db.query(CongestionScore)
        .filter_by(ba_id=ba.id, period_type=period_type)
    )
    if year:
        query = query.filter(
            CongestionScore.period_start >= f"{year}-01-01",
            CongestionScore.period_start < f"{year + 1}-01-01",
        )

    scores = query.order_by(CongestionScore.period_start).all()
    return [
        CongestionScoreResponse(
            ba_code=ba.ba_code,
            ba_name=ba.ba_name,
            region=ba.region,
            period_start=s.period_start,
            period_end=s.period_end,
            period_type=s.period_type,
            hours_total=s.hours_total,
            hours_importing=s.hours_importing,
            pct_hours_importing=s.pct_hours_importing,
            hours_above_80=s.hours_above_80,
            hours_above_90=s.hours_above_90,
            hours_above_95=s.hours_above_95,
            avg_import_pct_of_load=s.avg_import_pct_of_load,
            max_import_pct_of_load=s.max_import_pct_of_load,
            avg_congestion_premium=s.avg_congestion_premium,
            congestion_opportunity_score=s.congestion_opportunity_score,
            transfer_limit_used=s.transfer_limit_used,
            lmp_coverage=s.lmp_coverage,
            data_quality_flag=s.data_quality_flag,
        )
        for s in scores
    ]


@router.get("/duration-curve/{ba_code}", response_model=DurationCurveResponse)
@cache_response("congestion-duration", ttl=3600)
def get_duration_curve(
    ba_code: str,
    year: int = Query(2024, description="Year for duration curve"),
    request: Request = None,
    db: Session = Depends(get_db),
):
    """Get import utilization duration curve (sorted descending) for charting."""
    from core.congestion_calculator import compute_duration_curve

    ba = db.query(BalancingAuthority).filter_by(ba_code=ba_code.upper()).first()
    if not ba:
        raise HTTPException(status_code=404, detail=f"BA '{ba_code}' not found")

    if not ba.transfer_limit_mw or ba.transfer_limit_mw <= 0:
        raise HTTPException(
            status_code=400,
            detail=f"No transfer limit set for {ba_code}. Run estimate-limits first.",
        )

    hourly = (
        db.query(BAHourlyData)
        .filter(
            BAHourlyData.ba_id == ba.id,
            BAHourlyData.timestamp_utc >= f"{year}-01-01",
            BAHourlyData.timestamp_utc < f"{year + 1}-01-01",
        )
        .all()
    )

    if not hourly:
        raise HTTPException(
            status_code=404,
            detail=f"No hourly data for {ba_code} in {year}",
        )

    import pandas as pd
    df = pd.DataFrame([{
        "timestamp_utc": h.timestamp_utc,
        "net_imports_mw": h.net_imports_mw,
    } for h in hourly])

    values = compute_duration_curve(df, ba.transfer_limit_mw)

    return DurationCurveResponse(
        ba_code=ba.ba_code,
        ba_name=ba.ba_name,
        year=year,
        transfer_limit_mw=ba.transfer_limit_mw,
        values=values,
        hours_count=len(values),
    )


@router.get("/hourly/{ba_code}", response_model=list[HourlyDataResponse])
def get_hourly(
    ba_code: str,
    start: str = Query(..., description="Start date (YYYY-MM-DD)"),
    end: str = Query(..., description="End date (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
):
    """Get hourly operational data for a BA over a date range."""
    ba = db.query(BalancingAuthority).filter_by(ba_code=ba_code.upper()).first()
    if not ba:
        raise HTTPException(status_code=404, detail=f"BA '{ba_code}' not found")

    hourly = (
        db.query(BAHourlyData)
        .filter(
            BAHourlyData.ba_id == ba.id,
            BAHourlyData.timestamp_utc >= start,
            BAHourlyData.timestamp_utc <= end,
        )
        .order_by(BAHourlyData.timestamp_utc)
        .limit(8760)
        .all()
    )

    tl = ba.transfer_limit_mw
    return [
        HourlyDataResponse(
            timestamp_utc=h.timestamp_utc,
            demand_mw=h.demand_mw,
            net_generation_mw=h.net_generation_mw,
            total_interchange_mw=h.total_interchange_mw,
            net_imports_mw=h.net_imports_mw,
            import_utilization=(
                h.net_imports_mw / tl if tl and tl > 0 and h.net_imports_mw is not None else None
            ),
        )
        for h in hourly
    ]
