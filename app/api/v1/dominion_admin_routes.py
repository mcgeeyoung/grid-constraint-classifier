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


# ───────────────────────── events list + detail ─────────────────────────


def _zone_id_for(primary_pnode_id: str) -> Optional[str]:
    z = zone_for_pnode(load_zones(), str(primary_pnode_id))
    return z.id if z else None


def _pnode_name_for(session: Session, primary_pnode_id: str) -> Optional[str]:
    row = session.execute(
        select(DominionDevice.primary_pnode_name)
        .where(DominionDevice.primary_pnode_id == str(primary_pnode_id))
        .limit(1)
    ).scalar_one_or_none()
    return row


def _event_to_summary(ev, session: Session) -> AdminEventSummary:
    return AdminEventSummary(
        event_id=ev.event_id,
        device_id_external=ev.device_id_external,
        primary_pnode_id=ev.primary_pnode_id,
        primary_pnode_name=_pnode_name_for(session, ev.primary_pnode_id),
        zone_id=_zone_id_for(ev.primary_pnode_id),
        operating_date=ev.operating_date,
        start_utc=ev.start_utc,
        end_utc=ev.end_utc,
        duration_hours=ev.duration_hours,
        stressed_hours=ev.stressed_hours,
        extreme_hours=ev.extreme_hours,
        has_mandatory=ev.has_mandatory,
        listed_capacity_kw_avg=(
            ev.listed_capacity_kw * ev.avg_program_signal
            if ev.listed_capacity_kw is not None else None
        ),
        realized_capacity_kw_avg=ev.realized_capacity_kw_avg,
        performance_pct=ev.performance_pct,
        mandatory_performance_pct=ev.mandatory_performance_pct,
    )


@router.get("/events", response_model=AdminEventListResponse)
def list_events(
    window_days: int = Query(default=30, ge=1, le=365),
    zone_id: Optional[str] = None,
    has_mandatory: Optional[bool] = None,
    min_perf: Optional[float] = Query(default=None, ge=0, le=100),
    device_id_external: Optional[str] = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    latest = _latest_successful_run(db)
    if latest is None:
        return AdminEventListResponse(total=0, events=[])
    window_end = latest.operating_date
    window_start = window_end - timedelta(days=window_days - 1)

    device_ids: Optional[list[str]] = None
    if zone_id:
        z = load_zones().by_id(zone_id)
        if z is None:
            raise HTTPException(404, f"Zone {zone_id} not found")
        rows = db.execute(
            select(DominionDevice.device_id_external).where(
                DominionDevice.primary_pnode_id.in_(z.pnode_ids)
            )
        ).all()
        device_ids = [r[0] for r in rows]
        if not device_ids:
            return AdminEventListResponse(
                window_start=window_start, window_end=window_end, total=0, events=[]
            )
    if device_id_external:
        device_ids = [device_id_external] if device_ids is None else (
            [device_id_external] if device_id_external in device_ids else []
        )
        if not device_ids:
            return AdminEventListResponse(
                window_start=window_start, window_end=window_end, total=0, events=[]
            )

    events = build_events_for_window(
        db,
        window_start=window_start,
        window_end=window_end,
        device_ids=device_ids,
    )
    if has_mandatory is not None:
        events = [e for e in events if e.has_mandatory == has_mandatory]
    if min_perf is not None:
        events = [e for e in events if (e.performance_pct or 0) >= min_perf]

    events.sort(key=lambda e: e.start_utc, reverse=True)
    total = len(events)
    page = events[offset : offset + limit]
    return AdminEventListResponse(
        window_start=window_start,
        window_end=window_end,
        total=total,
        events=[_event_to_summary(e, db) for e in page],
    )


@router.get("/events/{event_id}", response_model=AdminEventDetail)
def get_event(event_id: str, db: Session = Depends(get_db)):
    # Event IDs are shaped: E-YYYY-MM-DD-<device_id>-<hh>
    # Parse the operating_date and device_id to scope the lookup cheaply.
    parts = event_id.split("-")
    if len(parts) < 6 or parts[0] != "E":
        raise HTTPException(400, f"Bad event_id: {event_id}")
    try:
        op_date = date.fromisoformat(f"{parts[1]}-{parts[2]}-{parts[3]}")
    except ValueError as e:
        raise HTTPException(400, f"Bad event_id date: {e}") from e
    start_hour_ept = parts[-1]
    device_id = "-".join(parts[4:-1])

    events = build_events_for_window(
        db,
        window_start=op_date,
        window_end=op_date,
        device_ids=[device_id],
        include_hourly_detail=True,
    )
    match = next((e for e in events if e.event_id == event_id), None)
    if match is None:
        raise HTTPException(404, f"Event {event_id} not found")

    summary = _event_to_summary(match, db)
    return AdminEventDetail(
        **summary.model_dump(),
        hours=[AdminEventHour(**h) for h in match.hours],
    )
