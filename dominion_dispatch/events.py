"""Materialize dispatch events from hourly schedule rows.

An "event" for this program is a contiguous run of non-normal dispatch
hours (stressed or extreme, with stressed and extreme hours allowed to
mix) for one device on one operating date. A 1-hour gap of normal
hours ends the event.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Iterable, Optional

from dominion_dispatch.telemetry_mock import mock_realized_kw


@dataclass(frozen=True)
class DispatchHourRow:
    device_id_external: str
    primary_pnode_id: str
    pjm_load_zone_code: str
    operating_date: date
    interval_start_utc: datetime
    period_tier: Optional[str]
    dispatch_signal: Optional[float]
    dispatch_signal_program: Optional[float]
    resolved_congestion: Optional[Decimal]
    dispatch_mandatory: Optional[bool]


@dataclass
class DeviceEvent:
    event_id: str
    device_id_external: str
    primary_pnode_id: str
    operating_date: date
    start_utc: datetime
    end_utc: datetime
    duration_hours: int
    stressed_hours: int
    extreme_hours: int
    has_mandatory: bool
    avg_program_signal: float
    listed_capacity_kw: Optional[float]
    realized_capacity_kw_avg: Optional[float]
    performance_pct: Optional[float]
    mandatory_performance_pct: Optional[float]
    hours: list[dict] = field(default_factory=list)


def _signal(v) -> float:
    if v is None:
        return 0.0
    return float(v)


def build_events_from_rows(
    rows: Iterable[DispatchHourRow],
    *,
    listed_capacity_kw: Optional[float] = None,
    include_hourly_detail: bool = False,
) -> list[DeviceEvent]:
    """Walk hourly rows (sorted) and emit contiguous non-normal events.

    When ``listed_capacity_kw`` is provided, realized telemetry is mocked
    and aggregated into performance columns on each event.
    """
    rows = sorted(rows, key=lambda r: (r.device_id_external, r.interval_start_utc))
    events: list[DeviceEvent] = []

    cur: list[DispatchHourRow] = []

    def close_current():
        if not cur:
            return
        first = cur[0]
        last = cur[-1]
        end_utc = last.interval_start_utc + timedelta(hours=1)
        start_local_hr = _ept_hour(first.interval_start_utc)
        stressed = sum(1 for r in cur if r.period_tier == "stressed")
        extreme = sum(1 for r in cur if r.period_tier == "extreme")
        avg_signal = (
            statistics.mean(_signal(r.dispatch_signal_program) for r in cur)
            if cur else 0.0
        )
        ev = DeviceEvent(
            event_id=f"E-{first.operating_date.isoformat()}-{first.device_id_external}-{start_local_hr:02d}",
            device_id_external=first.device_id_external,
            primary_pnode_id=first.primary_pnode_id,
            operating_date=first.operating_date,
            start_utc=first.interval_start_utc,
            end_utc=end_utc,
            duration_hours=len(cur),
            stressed_hours=stressed,
            extreme_hours=extreme,
            has_mandatory=extreme > 0,
            avg_program_signal=avg_signal,
            listed_capacity_kw=listed_capacity_kw,
            realized_capacity_kw_avg=None,
            performance_pct=None,
            mandatory_performance_pct=None,
        )
        if listed_capacity_kw is not None and listed_capacity_kw > 0:
            _attach_perf(ev, cur, float(listed_capacity_kw), include_hourly_detail)
        elif include_hourly_detail:
            ev.hours = [_hour_dict(i, r, None, None) for i, r in enumerate(cur)]
        events.append(ev)

    for r in rows:
        if r.period_tier in ("stressed", "extreme"):
            if cur and _is_contiguous(cur[-1], r):
                cur.append(r)
            else:
                close_current()
                cur = [r]
        else:
            close_current()
            cur = []
    close_current()
    return events


def _is_contiguous(prev: DispatchHourRow, nxt: DispatchHourRow) -> bool:
    return (
        nxt.device_id_external == prev.device_id_external
        and nxt.operating_date == prev.operating_date
        and nxt.interval_start_utc - prev.interval_start_utc == timedelta(hours=1)
    )


def _ept_hour(ts_utc: datetime) -> int:
    """Hour-of-day in Eastern Prevailing Time."""
    try:
        from zoneinfo import ZoneInfo
    except ImportError:
        ZoneInfo = None
    if ZoneInfo is not None:
        return ts_utc.astimezone(ZoneInfo("America/New_York")).hour
    # Fallback: UTC-5 rough approximation; acceptable for event naming only.
    return (ts_utc - timedelta(hours=5)).hour


def _attach_perf(
    ev: DeviceEvent,
    rows: list[DispatchHourRow],
    listed_kw: float,
    include_hourly_detail: bool,
) -> None:
    hour_rows: list[dict] = []
    realized_per_hour: list[float] = []
    realized_mandatory: list[float] = []

    for i, r in enumerate(rows):
        signal = _signal(r.dispatch_signal_program)
        realized_kw = mock_realized_kw(
            device_id_external=r.device_id_external,
            operating_date=r.operating_date,
            hour_index_in_event=i,
            period_tier=r.period_tier or "normal",
            listed_kw=listed_kw,
            dispatch_signal_program=signal,
            pnode_id_external=r.primary_pnode_id,
        )
        realized_per_hour.append(realized_kw)
        if r.period_tier == "extreme":
            realized_mandatory.append(realized_kw)
        hour_rows.append(_hour_dict(i, r, listed_kw * signal, realized_kw))

    listed_avg_kw = listed_kw * ev.avg_program_signal
    realized_avg_kw = statistics.mean(realized_per_hour) if realized_per_hour else 0.0

    ev.realized_capacity_kw_avg = realized_avg_kw
    ev.performance_pct = (
        100.0 * realized_avg_kw / listed_avg_kw if listed_avg_kw > 0 else None
    )

    if realized_mandatory:
        mand_signals = [
            _signal(r.dispatch_signal_program) for r in rows if r.period_tier == "extreme"
        ]
        mand_listed = listed_kw * (statistics.mean(mand_signals) if mand_signals else 0)
        mand_realized = statistics.mean(realized_mandatory)
        ev.mandatory_performance_pct = (
            100.0 * mand_realized / mand_listed if mand_listed > 0 else None
        )

    if include_hourly_detail:
        ev.hours = hour_rows


def _hour_dict(
    idx: int,
    r: DispatchHourRow,
    listed_kw_ask: Optional[float],
    realized_kw: Optional[float],
) -> dict:
    return {
        "hour_index": idx,
        "interval_start_utc": r.interval_start_utc.isoformat(),
        "period_tier": r.period_tier,
        "dispatch_signal_program": _signal(r.dispatch_signal_program),
        "listed_kw_ask": listed_kw_ask,
        "realized_kw": realized_kw,
    }


from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from app.models.dominion_der import (
    DominionDaIngestionRun,
    DominionDevice,
    DominionDispatchDeviceHour,
)


def fetch_hours_for_window(
    session: Session,
    *,
    window_start: date,
    window_end: date,
    device_ids: Optional[list[str]] = None,
) -> list[DispatchHourRow]:
    """Pull dispatch hours joined to ingestion-run operating_date.

    Returns non-normal hours only (stressed or extreme), sorted by
    (device_id_external, interval_start_utc).
    """
    q = (
        select(
            DominionDispatchDeviceHour.device_id_external,
            DominionDispatchDeviceHour.primary_pnode_id,
            DominionDispatchDeviceHour.pjm_load_zone_code,
            DominionDaIngestionRun.operating_date,
            DominionDispatchDeviceHour.interval_start_utc,
            DominionDispatchDeviceHour.period_tier,
            DominionDispatchDeviceHour.dispatch_signal,
            DominionDispatchDeviceHour.dispatch_signal_program,
            DominionDispatchDeviceHour.resolved_congestion,
            DominionDispatchDeviceHour.dispatch_mandatory,
        )
        .join(
            DominionDaIngestionRun,
            DominionDaIngestionRun.id == DominionDispatchDeviceHour.ingestion_run_id,
        )
        .where(
            and_(
                DominionDaIngestionRun.operating_date >= window_start,
                DominionDaIngestionRun.operating_date <= window_end,
                DominionDispatchDeviceHour.period_tier.in_(("stressed", "extreme")),
            )
        )
        .order_by(
            DominionDispatchDeviceHour.device_id_external,
            DominionDispatchDeviceHour.interval_start_utc,
        )
    )
    if device_ids:
        q = q.where(DominionDispatchDeviceHour.device_id_external.in_(device_ids))

    return [DispatchHourRow(**dict(r._mapping)) for r in session.execute(q).all()]


def device_capacity_map(session: Session, device_ids: list[str]) -> dict[str, float]:
    if not device_ids:
        return {}
    rows = session.execute(
        select(DominionDevice.device_id_external, DominionDevice.listed_capacity_kw)
        .where(DominionDevice.device_id_external.in_(device_ids))
    ).all()
    return {r[0]: float(r[1]) for r in rows if r[1] is not None}


def build_events_for_window(
    session: Session,
    *,
    window_start: date,
    window_end: date,
    device_ids: Optional[list[str]] = None,
    include_hourly_detail: bool = False,
) -> list[DeviceEvent]:
    """Fetch hours, group by device, materialize events per device."""
    rows = fetch_hours_for_window(
        session,
        window_start=window_start,
        window_end=window_end,
        device_ids=device_ids,
    )
    if not rows:
        return []

    all_ids = sorted({r.device_id_external for r in rows})
    caps = device_capacity_map(session, all_ids)

    events: list[DeviceEvent] = []
    cur_id: Optional[str] = None
    cur_rows: list[DispatchHourRow] = []
    for r in rows:
        if r.device_id_external != cur_id:
            if cur_rows:
                events.extend(
                    build_events_from_rows(
                        cur_rows,
                        listed_capacity_kw=caps.get(cur_id or ""),
                        include_hourly_detail=include_hourly_detail,
                    )
                )
            cur_id = r.device_id_external
            cur_rows = []
        cur_rows.append(r)
    if cur_rows:
        events.extend(
            build_events_from_rows(
                cur_rows,
                listed_capacity_kw=caps.get(cur_id or ""),
                include_hourly_detail=include_hourly_detail,
            )
        )
    return events
