"""Per-device dispatch participation rollup over a window of DA operating days."""

from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import date, timedelta
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.dominion_der import (
    DominionDaIngestionRun,
    DominionDispatchDeviceHour,
)


@dataclass
class DeviceParticipation:
    device_id_external: str
    runs: int
    total_hours: int
    normal_hours: int
    stressed_hours: int
    extreme_hours: int
    mandatory_hours: int
    any_dispatch_hours: int
    participation_pct: float
    mandatory_pct: float
    window_start: Optional[date]
    window_end: Optional[date]

    def as_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["window_start"] = self.window_start.isoformat() if self.window_start else None
        d["window_end"] = self.window_end.isoformat() if self.window_end else None
        return d


def compute_participation_for_devices(
    session: Session,
    device_ids: list[str],
    *,
    window_days: int = 30,
    as_of: Optional[date] = None,
) -> dict[str, DeviceParticipation]:
    """
    Aggregate dispatch rows for `device_ids` over the last `window_days` DA
    operating days (by ``dominion_da_ingestion_runs.operating_date``) ending at
    ``as_of`` (inclusive; defaults to max operating_date present).

    Counts are in hours (one dispatch row == one operating hour).
    """
    if not device_ids:
        return {}

    # Anchor window on the most recent operating_date that actually contributed
    # dispatch rows. Ingests with zero PJM rows (e.g. future dates) would pull
    # the window forward and shrink the effective history.
    max_op = session.execute(
        select(func.max(DominionDaIngestionRun.operating_date))
        .join(
            DominionDispatchDeviceHour,
            DominionDispatchDeviceHour.ingestion_run_id == DominionDaIngestionRun.id,
        )
    ).scalar_one_or_none()
    if max_op is None:
        # No ingests yet; return empty rollups so callers can still render
        return {
            did: DeviceParticipation(
                device_id_external=did,
                runs=0,
                total_hours=0,
                normal_hours=0,
                stressed_hours=0,
                extreme_hours=0,
                mandatory_hours=0,
                any_dispatch_hours=0,
                participation_pct=0.0,
                mandatory_pct=0.0,
                window_start=None,
                window_end=None,
            )
            for did in device_ids
        }

    end = as_of if as_of is not None else max_op
    start = end - timedelta(days=window_days - 1)

    # Subquery: ingestion_run_ids inside the window
    run_ids_q = (
        select(DominionDaIngestionRun.id)
        .where(
            DominionDaIngestionRun.operating_date >= start,
            DominionDaIngestionRun.operating_date <= end,
            DominionDaIngestionRun.status == "success",
        )
        .scalar_subquery()
    )

    # Count only runs that contributed dispatch rows; a "success" ingest with
    # zero PJM rows (e.g., future date) would otherwise inflate this.
    runs_in_window = session.execute(
        select(func.count(func.distinct(DominionDispatchDeviceHour.ingestion_run_id)))
        .join(
            DominionDaIngestionRun,
            DominionDaIngestionRun.id == DominionDispatchDeviceHour.ingestion_run_id,
        )
        .where(
            DominionDaIngestionRun.operating_date >= start,
            DominionDaIngestionRun.operating_date <= end,
            DominionDaIngestionRun.status == "success",
        )
    ).scalar_one()

    # Per-device tier counts
    tier_col = DominionDispatchDeviceHour.period_tier
    mandatory_col = DominionDispatchDeviceHour.dispatch_mandatory

    rows = session.execute(
        select(
            DominionDispatchDeviceHour.device_id_external,
            tier_col,
            mandatory_col,
            func.count().label("n"),
        )
        .where(
            DominionDispatchDeviceHour.ingestion_run_id.in_(run_ids_q),
            DominionDispatchDeviceHour.device_id_external.in_(device_ids),
        )
        .group_by(
            DominionDispatchDeviceHour.device_id_external,
            tier_col,
            mandatory_col,
        )
    ).all()

    init = {
        did: {
            "total": 0, "normal": 0, "stressed": 0, "extreme": 0, "mandatory": 0,
        }
        for did in device_ids
    }
    for did, tier, mandatory, n in rows:
        if did not in init:
            continue
        init[did]["total"] += n
        if tier == "normal":
            init[did]["normal"] += n
        elif tier == "stressed":
            init[did]["stressed"] += n
        elif tier == "extreme":
            init[did]["extreme"] += n
        if mandatory:
            init[did]["mandatory"] += n

    out: dict[str, DeviceParticipation] = {}
    for did in device_ids:
        d = init[did]
        any_dispatch = d["stressed"] + d["extreme"]
        total = d["total"]
        out[did] = DeviceParticipation(
            device_id_external=did,
            runs=runs_in_window,
            total_hours=total,
            normal_hours=d["normal"],
            stressed_hours=d["stressed"],
            extreme_hours=d["extreme"],
            mandatory_hours=d["mandatory"],
            any_dispatch_hours=any_dispatch,
            participation_pct=100.0 * any_dispatch / total if total else 0.0,
            mandatory_pct=100.0 * d["mandatory"] / total if total else 0.0,
            window_start=start,
            window_end=end,
        )
    return out
