"""Admin routes: computation management and system operations."""

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.auth import require_api_key
from app.database import get_db
from app.models.computation_run import ComputationRun

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.post("/recompute")
async def recompute_profiles(
    iso_code: Optional[str] = None,
    year: Optional[int] = 2024,
    api_key: str = Depends(require_api_key),
    db: Session = Depends(get_db),
):
    """Trigger profile recomputation via profile_engine."""
    from core.profile_engine import run_full_pipeline

    run = run_full_pipeline(db, iso_code=iso_code, year=year)
    return {
        "run_id": run.id,
        "status": run.status,
        "metrics": run.metrics_json,
    }


@router.post("/refresh-matviews")
async def refresh_matviews(
    api_key: str = Depends(require_api_key),
    db: Session = Depends(get_db),
):
    """Refresh materialized views."""
    from core.profile_engine import refresh_materialized_views
    refresh_materialized_views(db)
    return {"status": "ok"}


@router.get("/computation-runs")
async def list_runs(
    limit: int = Query(20, le=100),
    db: Session = Depends(get_db),
):
    """List recent computation runs with metrics."""
    runs = (
        db.query(ComputationRun)
        .order_by(ComputationRun.started_at.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": r.id,
            "run_type": r.run_type,
            "iso_id": r.iso_id,
            "period_year": r.period_year,
            "started_at": r.started_at.isoformat() if r.started_at else None,
            "completed_at": r.completed_at.isoformat() if r.completed_at else None,
            "status": r.status,
            "metrics": r.metrics_json,
            "error": r.error_message,
        }
        for r in runs
    ]
