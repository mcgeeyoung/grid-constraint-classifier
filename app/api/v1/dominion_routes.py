"""Dominion DER demo: live PJM ingest + DB-backed dispatch, for FastAPI + static UI."""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.dominion_der import (
    DominionDaIngestionRun,
    DominionDevice,
    DominionDispatchDeviceHour,
)
from app.schemas.dominion import (
    DominionDeviceResponse,
    DominionDispatchHourResponse,
    DominionDispatchRebuildRequest,
    DominionDispatchRebuildResponse,
    DominionIngestRequest,
    DominionIngestionRunResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter()


def _run_to_response(run: DominionDaIngestionRun) -> DominionIngestionRunResponse:
    return DominionIngestionRunResponse(
        id=run.id,
        operating_date=run.operating_date,
        zone_code=run.zone_code,
        lmp_type=run.lmp_type,
        status=run.status,
        retrieved_at_utc=run.retrieved_at_utc,
        row_count=run.row_count,
        error_message=run.error_message,
        idempotency_key=run.idempotency_key,
    )


@router.get("/ingestion-runs", response_model=list[DominionIngestionRunResponse])
def list_dominion_ingestion_runs(
    limit: int = Query(default=40, le=200),
    db: Session = Depends(get_db),
):
    rows = (
        db.execute(
            select(DominionDaIngestionRun).order_by(DominionDaIngestionRun.id.desc()).limit(limit)
        )
        .scalars()
        .all()
    )
    return [_run_to_response(r) for r in rows]


@router.get("/ingestion-runs/{run_id}", response_model=DominionIngestionRunResponse)
def get_dominion_ingestion_run(run_id: int, db: Session = Depends(get_db)):
    run = db.get(DominionDaIngestionRun, run_id)
    if run is None:
        raise HTTPException(404, f"Ingestion run {run_id} not found")
    return _run_to_response(run)


@router.post("/ingest", response_model=DominionIngestionRunResponse)
def ingest_dominion_da(body: DominionIngestRequest, db: Session = Depends(get_db)):
    """
    Pull PJM ``da_hrl_lmps`` for zone DOM and persist node hourly rows + run metadata.

    Requires ``PJM_SUBSCRIPTION_KEY``. Idempotent per (zone, lmp_type, operating_date)
    unless ``replace_existing`` is true.
    """
    if not settings.PJM_SUBSCRIPTION_KEY.strip():
        raise HTTPException(
            503,
            "PJM_SUBSCRIPTION_KEY is not set; configure the environment for live ingest.",
        )
    from src.pjm_client import PJMClient

    from dominion_dispatch.da_congestion import fetch_da_node_congestion_dom
    from dominion_dispatch.persist import ingest_da_dom_dataframe

    client = PJMClient(settings.PJM_SUBSCRIPTION_KEY)
    try:
        df = fetch_da_node_congestion_dom(
            client,
            body.operating_date,
            lmp_type=body.lmp_type,
            zone=body.zone_code,
        )
    except Exception as e:
        logger.exception("PJM fetch failed")
        raise HTTPException(502, f"PJM fetch failed: {e}") from e

    try:
        run = ingest_da_dom_dataframe(
            db,
            df,
            body.operating_date,
            zone_code=body.zone_code,
            lmp_type=body.lmp_type,
            replace_existing=body.replace_existing,
        )
        db.commit()
        db.refresh(run)
    except Exception:
        db.rollback()
        raise
    return _run_to_response(run)


@router.get("/devices", response_model=list[DominionDeviceResponse])
def list_dominion_devices(
    as_of: Optional[date] = Query(
        default=None,
        description="Enrollment window filter (defaults to today UTC date)",
    ),
    db: Session = Depends(get_db),
):
    d = as_of or datetime.now(timezone.utc).date()
    rows = db.execute(
        select(DominionDevice).where(
            DominionDevice.effective_from <= d,
            or_(DominionDevice.effective_to.is_(None), DominionDevice.effective_to >= d),
        )
    ).scalars().all()
    return [
        DominionDeviceResponse(
            device_id_external=r.device_id_external,
            pjm_load_zone_code=r.pjm_load_zone_code,
            primary_pnode_id=r.primary_pnode_id,
            primary_pnode_name=r.primary_pnode_name,
            asset_lat=r.asset_lat,
            asset_lon=r.asset_lon,
            asset_display_name=r.asset_display_name,
            effective_from=r.effective_from,
            effective_to=r.effective_to,
        )
        for r in rows
    ]


@router.get("/dispatch", response_model=list[DominionDispatchHourResponse])
def list_dominion_dispatch_hours(
    ingestion_run_id: int = Query(..., description="FK to dominion_da_ingestion_runs.id"),
    device_id_external: Optional[str] = Query(default=None),
    limit: int = Query(default=8000, le=50_000),
    db: Session = Depends(get_db),
):
    run = db.get(DominionDaIngestionRun, ingestion_run_id)
    if run is None:
        raise HTTPException(404, f"Ingestion run {ingestion_run_id} not found")

    q = select(DominionDispatchDeviceHour).where(
        DominionDispatchDeviceHour.ingestion_run_id == ingestion_run_id
    )
    if device_id_external:
        q = q.where(DominionDispatchDeviceHour.device_id_external == device_id_external)
    q = q.order_by(
        DominionDispatchDeviceHour.device_id_external,
        DominionDispatchDeviceHour.interval_start_utc,
    ).limit(limit)
    rows = db.execute(q).scalars().all()
    out: list[DominionDispatchHourResponse] = []
    for r in rows:
        out.append(
            DominionDispatchHourResponse(
                device_id_external=r.device_id_external,
                primary_pnode_id=r.primary_pnode_id,
                interval_start_utc=r.interval_start_utc,
                raw_congestion=float(r.raw_congestion) if r.raw_congestion is not None else None,
                resolved_congestion=float(r.resolved_congestion)
                if r.resolved_congestion is not None
                else None,
                resolution_strategy=r.resolution_strategy,
                dispatch_signal=float(r.dispatch_signal) if r.dispatch_signal is not None else None,
                extreme_abs_threshold_usd=float(r.extreme_abs_threshold_usd)
                if r.extreme_abs_threshold_usd is not None
                else None,
                period_tier=r.period_tier,
                dispatch_mandatory=r.dispatch_mandatory,
                dispatch_signal_program=float(r.dispatch_signal_program)
                if r.dispatch_signal_program is not None
                else None,
            )
        )
    return out


@router.post("/dispatch/rebuild", response_model=DominionDispatchRebuildResponse)
def rebuild_dominion_dispatch(body: DominionDispatchRebuildRequest, db: Session = Depends(get_db)):
    """
    Recompute ``build_dispatch_schedule`` from DB hourly + active devices, then persist.
    """
    from dominion_dispatch.dispatch_schedule import build_dispatch_schedule
    from dominion_dispatch.persist_schedule import (
        fetch_active_devices_for_schedule,
        fetch_hourly_dataframe_for_run,
        persist_dispatch_schedule,
    )

    run = db.get(DominionDaIngestionRun, body.ingestion_run_id)
    if run is None:
        raise HTTPException(404, f"Ingestion run {body.ingestion_run_id} not found")

    devices = fetch_active_devices_for_schedule(db, run.operating_date)
    if not devices:
        raise HTTPException(
            400,
            "No active dominion_devices for this operating date; seed enrollment first.",
        )

    hourly_df = fetch_hourly_dataframe_for_run(db, body.ingestion_run_id)
    if hourly_df.empty:
        raise HTTPException(
            400,
            "No hourly rows for this ingestion run; ingest DA node data first.",
        )

    schedule = build_dispatch_schedule(
        devices,
        hourly_df,
        enable_period_policy=not body.no_period_policy,
        stressed_abs_threshold_usd=body.stressed_threshold_usd,
        extreme_abs_quantile=body.extreme_quantile,
        stressed_signal_fraction=body.stressed_signal_fraction,
        stressed_peak_only=body.stressed_peak_only,
    )

    try:
        n = persist_dispatch_schedule(
            db,
            body.ingestion_run_id,
            schedule,
            replace_existing=body.replace_existing,
        )
        db.commit()
    except Exception:
        db.rollback()
        raise

    return DominionDispatchRebuildResponse(
        ingestion_run_id=body.ingestion_run_id,
        rows_persisted=n,
        device_count=len(devices),
    )


@router.get("/asset-map", response_class=HTMLResponse)
def dominion_asset_map_html(
    as_of: Optional[date] = Query(
        default=None,
        description="Enrollment as-of date for devices on the map",
    ),
    db: Session = Depends(get_db),
):
    """Interactive Folium map (DER sites vs pnodes) for devices active on ``as_of``."""
    from dominion_dispatch.asset_map import build_dom_program_asset_nodal_map
    from dominion_dispatch.persist_schedule import fetch_active_devices_for_schedule

    d = as_of or datetime.now(timezone.utc).date()
    devices = fetch_active_devices_for_schedule(db, d)
    if not devices:
        return HTMLResponse(
            "<html><body><p>No active devices for this date.</p></body></html>",
            status_code=200,
        )

    with TemporaryDirectory() as td:
        out = Path(td) / "dominion_assets.html"
        build_dom_program_asset_nodal_map(
            devices,
            project_root=settings.PROJECT_ROOT,
            output_html=out,
            session=db,
            include_dom_boundary=True,
            geocode_missing_pnodes=False,
        )
        html = out.read_text(encoding="utf-8")
    return HTMLResponse(html)
