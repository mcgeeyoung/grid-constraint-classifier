"""Monitoring, quality metrics, and operational health API routes.

Endpoints:
  GET  /api/v1/monitor/health        - Deep health check (DB + Redis)
  GET  /api/v1/monitor/coverage      - Data coverage summary
  GET  /api/v1/monitor/staleness     - Data staleness report
  GET  /api/v1/monitor/jobs          - Recent monitor job history
  GET  /api/v1/monitor/quality       - Data quality metrics
  POST /api/v1/monitor/jobs/{id}/run - Trigger a job manually (admin)
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import distinct, func
from sqlalchemy.orm import Session

from app.auth import require_api_key
from app.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/monitor", tags=["monitoring"])


@router.get("/health")
def deep_health_check(db: Session = Depends(get_db)):
    """Deep health check: DB connectivity, Redis, data freshness."""
    checks = {}

    # Database
    try:
        from sqlalchemy import text
        db.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as e:
        checks["database"] = f"error: {e}"

    # Redis
    try:
        from app.cache import get_redis
        r = get_redis()
        if r and r.ping():
            checks["redis"] = "ok"
        else:
            checks["redis"] = "unavailable"
    except Exception as e:
        checks["redis"] = f"error: {e}"

    # Table counts (quick data presence check)
    try:
        from app.models import Utility, HostingCapacityRecord, ISO
        checks["utilities"] = db.query(Utility).count()
        checks["hc_records"] = db.query(HostingCapacityRecord).count()
        checks["isos"] = db.query(ISO).count()
    except Exception:
        checks["data"] = "error reading counts"

    all_ok = checks.get("database") == "ok"
    status_code = 200 if all_ok else 503

    return {
        "status": "healthy" if all_ok else "degraded",
        "checks": checks,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/coverage")
def coverage_summary(
    state: Optional[str] = Query(None, description="Filter by state"),
    data_type: Optional[str] = Query(None, description="Filter by data type"),
    db: Session = Depends(get_db),
):
    """Data coverage summary across utilities and data types."""
    from app.models import (
        Utility, HostingCapacityRecord, GridConstraint,
        LoadForecast, ResourceNeed, InterconnectionQueue,
    )

    # Overall counts
    summary = {
        "total_utilities": db.query(Utility).count(),
        "utilities_with_eia_id": db.query(Utility).filter(
            Utility.eia_id.isnot(None)
        ).count(),
        "states_with_data": db.query(distinct(Utility.state)).filter(
            Utility.state.isnot(None)
        ).count(),
    }

    # Per data-type counts
    type_counts = {}
    models = {
        "hosting_capacity": HostingCapacityRecord,
        "grid_constraint": GridConstraint,
        "load_forecast": LoadForecast,
        "resource_need": ResourceNeed,
        "interconnection_queue": InterconnectionQueue,
    }

    for dtype, model in models.items():
        if data_type and dtype != data_type:
            continue

        q = db.query(model)
        if state and hasattr(model, "utility"):
            q = q.join(Utility).filter(Utility.state == state)

        type_counts[dtype] = {
            "total_records": q.count(),
            "utilities_with_data": (
                db.query(distinct(model.utility_id))
                .filter(model.utility_id.isnot(None))
                .count()
            ),
        }

    summary["data_types"] = type_counts

    # State breakdown if requested
    if state:
        state_utils = (
            db.query(Utility)
            .filter(Utility.state == state)
            .all()
        )
        summary["state_detail"] = {
            "state": state,
            "utility_count": len(state_utils),
            "utilities": [
                {"id": u.id, "name": u.utility_name, "eia_id": u.eia_id}
                for u in state_utils[:25]
            ],
        }

    return summary


@router.get("/staleness")
def staleness_report(
    threshold_days: int = Query(180, description="Days before data is considered stale"),
    db: Session = Depends(get_db),
):
    """Report on data staleness across coverage records."""
    from app.models import DataCoverage

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=threshold_days)

    total = db.query(DataCoverage).filter(DataCoverage.has_data == True).count()

    stale = (
        db.query(DataCoverage)
        .filter(
            DataCoverage.has_data == True,
            DataCoverage.last_updated_at < cutoff,
        )
        .all()
    )

    never_checked = (
        db.query(DataCoverage)
        .filter(
            DataCoverage.has_data == True,
            DataCoverage.last_checked_at.is_(None),
        )
        .count()
    )

    return {
        "threshold_days": threshold_days,
        "total_with_data": total,
        "stale_count": len(stale),
        "never_checked": never_checked,
        "stale_items": [
            {
                "entity_type": s.entity_type,
                "entity_name": s.entity_name,
                "data_type": s.data_type,
                "last_updated": s.last_updated_at.isoformat() if s.last_updated_at else None,
                "age_days": (now - s.last_updated_at).days if s.last_updated_at else None,
            }
            for s in stale[:50]
        ],
    }


@router.get("/jobs")
def recent_jobs(
    limit: int = Query(25, le=100),
    job_name: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """Recent monitor job execution history."""
    from app.models import MonitorEvent

    q = db.query(MonitorEvent).order_by(MonitorEvent.started_at.desc())

    if job_name:
        q = q.filter(MonitorEvent.job_name == job_name)

    events = q.limit(limit).all()

    return {
        "count": len(events),
        "events": [
            {
                "id": e.id,
                "job_name": e.job_name,
                "status": e.status,
                "started_at": e.started_at.isoformat(),
                "completed_at": e.completed_at.isoformat() if e.completed_at else None,
                "duration_sec": e.duration_sec,
                "records_checked": e.records_checked,
                "records_updated": e.records_updated,
                "new_items_found": e.new_items_found,
                "alerts_generated": e.alerts_generated,
                "summary": e.summary,
                "error_message": e.error_message,
            }
            for e in events
        ],
    }


@router.get("/quality")
def quality_metrics(db: Session = Depends(get_db)):
    """Data quality metrics: coverage, freshness, completeness."""
    from app.models import (
        Utility, DataCoverage, HostingCapacityRecord,
        GridConstraint, LoadForecast, MonitorEvent,
    )

    now = datetime.now(timezone.utc)

    # Coverage: what % of utilities have each data type
    total_utilities = db.query(Utility).count() or 1

    coverage = {}
    for dtype, model in [
        ("hosting_capacity", HostingCapacityRecord),
        ("grid_constraint", GridConstraint),
        ("load_forecast", LoadForecast),
    ]:
        utils_with_data = (
            db.query(distinct(model.utility_id))
            .filter(model.utility_id.isnot(None))
            .count()
        )
        coverage[dtype] = {
            "utilities_with_data": utils_with_data,
            "coverage_pct": round(utils_with_data / total_utilities * 100, 1),
        }

    # Recent job success rate
    week_ago = now - timedelta(days=7)
    recent_jobs = (
        db.query(MonitorEvent)
        .filter(MonitorEvent.started_at >= week_ago)
        .all()
    )
    total_jobs = len(recent_jobs)
    successful = sum(1 for j in recent_jobs if j.status == "success")
    job_health = {
        "total_last_7d": total_jobs,
        "successful": successful,
        "success_rate_pct": round(successful / total_jobs * 100, 1) if total_jobs else 0,
    }

    return {
        "timestamp": now.isoformat(),
        "total_utilities": total_utilities,
        "coverage_by_type": coverage,
        "job_health": job_health,
    }


@router.post("/jobs/{job_id}/run", dependencies=[Depends(require_api_key)])
def trigger_job(job_id: str, db: Session = Depends(get_db)):
    """Manually trigger a monitoring job (requires API key)."""
    from app.scheduler import JOB_REGISTRY

    job = next((j for j in JOB_REGISTRY if j["id"] == job_id), None)
    if not job:
        available = [j["id"] for j in JOB_REGISTRY]
        raise HTTPException(404, f"Job '{job_id}' not found. Available: {available}")

    try:
        job["func"]()
        return {"status": "completed", "job_id": job_id}
    except Exception as e:
        raise HTTPException(500, f"Job failed: {e}")
