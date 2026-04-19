"""Dominion admin dashboard API (demo prop)."""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.dominion_der import (
    DominionDaIngestionRun,
    DominionDaNodeHourly,
    DominionDevice,
    DominionDispatchDeviceHour,
)
from app.schemas.dominion import (
    AdminDashboardHour,
    AdminDashboardToday,
    AdminDashboardZoneSlice,
    AdminDeviceRecentEvent,
    AdminDeviceSummary,
    AdminEventDetail,
    AdminEventHour,
    AdminEventListResponse,
    AdminEventSummary,
    AdminZoneDetail,
    AdminZoneSummary,
    DominionDeviceResponse,
)
from dominion_dispatch.events import (
    build_events_for_window,
    fetch_hours_for_window,
)
from dominion_dispatch.zones import Zone, load_zones, zone_for_pnode

logger = logging.getLogger(__name__)

router = APIRouter()


# ───────────────────────── helpers ─────────────────────────


def _active_devices(session: Session, as_of: date) -> list[DominionDevice]:
    from sqlalchemy import or_
    rows = session.execute(
        select(DominionDevice).where(
            DominionDevice.effective_from <= as_of,
            or_(DominionDevice.effective_to.is_(None), DominionDevice.effective_to >= as_of),
        )
    ).scalars().all()
    return list(rows)


def _device_response(d: DominionDevice) -> DominionDeviceResponse:
    return DominionDeviceResponse.model_validate(d, from_attributes=True)


def _latest_successful_run(session: Session) -> Optional[DominionDaIngestionRun]:
    return session.execute(
        select(DominionDaIngestionRun)
        .where(
            DominionDaIngestionRun.status == "success",
            DominionDaIngestionRun.row_count > 0,
        )
        .order_by(DominionDaIngestionRun.operating_date.desc())
        .limit(1)
    ).scalar_one_or_none()


def _run_for_date(session: Session, d: date) -> Optional[DominionDaIngestionRun]:
    return session.execute(
        select(DominionDaIngestionRun)
        .where(
            DominionDaIngestionRun.operating_date == d,
            DominionDaIngestionRun.status == "success",
            DominionDaIngestionRun.row_count > 0,
        )
        .order_by(DominionDaIngestionRun.id.desc())
        .limit(1)
    ).scalar_one_or_none()


def _utcnow_date() -> date:
    return datetime.now(timezone.utc).date()


# ───────────────────────── zones ─────────────────────────


@router.get("/zones", response_model=list[AdminZoneSummary])
def list_zones(db: Session = Depends(get_db)):
    idx = load_zones()
    as_of = _utcnow_date()
    devices = _active_devices(db, as_of)
    caps = {
        d.device_id_external: float(d.listed_capacity_kw) if d.listed_capacity_kw is not None else 0.0
        for d in devices
    }
    by_pnode = {d.primary_pnode_id: d for d in devices}

    out: list[AdminZoneSummary] = []
    for z in idx.zones:
        zone_devices = [by_pnode[pid] for pid in z.pnode_ids if pid in by_pnode]
        listed = sum(caps.get(d.device_id_external, 0.0) for d in zone_devices)
        out.append(
            AdminZoneSummary(
                id=z.id,
                label=z.label,
                description=z.description,
                pnode_ids=list(z.pnode_ids),
                device_ids=[d.device_id_external for d in zone_devices],
                device_count=len(zone_devices),
                listed_capacity_kw=listed,
            )
        )
    return out


@router.get("/zones/{zone_id}", response_model=AdminZoneDetail)
def get_zone(zone_id: str, db: Session = Depends(get_db)):
    idx = load_zones()
    z = idx.by_id(zone_id)
    if z is None:
        raise HTTPException(404, f"Zone {zone_id} not found")
    as_of = _utcnow_date()
    devices = _active_devices(db, as_of)
    zone_devices = [d for d in devices if d.primary_pnode_id in z.pnode_ids]
    listed = sum(
        float(d.listed_capacity_kw) if d.listed_capacity_kw is not None else 0.0
        for d in zone_devices
    )
    return AdminZoneDetail(
        id=z.id,
        label=z.label,
        description=z.description,
        pnode_ids=list(z.pnode_ids),
        device_ids=[d.device_id_external for d in zone_devices],
        device_count=len(zone_devices),
        listed_capacity_kw=listed,
        devices=[_device_response(d) for d in zone_devices],
    )


# ───────────────────────── dashboard/today ─────────────────────────


@router.get("/dashboard/today", response_model=AdminDashboardToday)
def dashboard_today(db: Session = Depends(get_db)):
    idx = load_zones()
    as_of = _utcnow_date()

    tomorrow_run = _run_for_date(db, as_of + timedelta(days=1))
    if tomorrow_run:
        run = tomorrow_run
        basis = "tomorrow_da"
    else:
        run = _latest_successful_run(db)
        basis = "most_recent_da"
    if run is None:
        raise HTTPException(503, "No successful DA ingest available yet.")

    events = build_events_for_window(
        db,
        window_start=run.operating_date,
        window_end=run.operating_date,
    )

    # Per-zone rollups
    by_zone_buf: dict[str, dict] = {z.id: {"events": 0, "peak_kw": 0.0} for z in idx.zones}
    for ev in events:
        zone = zone_for_pnode(idx, ev.primary_pnode_id)
        zid = zone.id if zone else None
        if not zid:
            continue
        by_zone_buf[zid]["events"] += 1
        peak = (ev.listed_capacity_kw or 0.0) * max(
            (h["dispatch_signal_program"] for h in (ev.hours or [{"dispatch_signal_program": ev.avg_program_signal}])),
            default=0.0,
        )
        if peak > by_zone_buf[zid]["peak_kw"]:
            by_zone_buf[zid]["peak_kw"] = peak

    # Fleet 24-hour signal series
    hour_rows = fetch_hours_for_window(
        db, window_start=run.operating_date, window_end=run.operating_date
    )
    hour_map: dict[datetime, list[float]] = {}
    for r in hour_rows:
        hour_map.setdefault(r.interval_start_utc, []).append(r.dispatch_signal_program or 0.0)
    fleet_series = [
        AdminDashboardHour(hour_utc=ts, program_signal=sum(vals) / len(vals))
        for ts, vals in sorted(hour_map.items())
    ]

    events_forecast = sum(1 for ev in events)
    peak_kw = max(
        (
            (ev.listed_capacity_kw or 0.0) * ev.avg_program_signal
            for ev in events
        ),
        default=0.0,
    )

    return AdminDashboardToday(
        operating_date=run.operating_date,
        forecast_basis=basis,
        ingestion_run_id=run.id,
        events_forecast=events_forecast,
        peak_program_kw=peak_kw,
        peak_window_ept=None,
        by_zone=[
            AdminDashboardZoneSlice(zone_id=zid, events=v["events"], peak_kw=v["peak_kw"])
            for zid, v in by_zone_buf.items()
        ],
        fleet_24h_signal=fleet_series,
    )
