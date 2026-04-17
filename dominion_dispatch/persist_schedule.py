"""
Write ``build_dispatch_schedule`` output to Postgres (``dominion_dispatch_device_hourly``).
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Any, Optional

import pandas as pd
from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from app.models.dominion_der import (
    DominionDaIngestionRun,
    DominionDaNodeHourly,
    DominionDevice,
    DominionDispatchDeviceHour,
)
from dominion_dispatch.config import PJM_ZONE_DOM

logger = logging.getLogger(__name__)

BATCH = 4000


def schedule_interval_to_utc(ts: Any) -> datetime:
    """Normalize schedule ``interval_start`` (naive EPT or aware) to UTC ``datetime``."""
    t = pd.Timestamp(ts)
    if t.tzinfo is None:
        t = t.tz_localize(
            "America/New_York",
            ambiguous="infer",
            nonexistent="shift_forward",
        )
    return t.tz_convert("UTC").to_pydatetime()


def _num_or_none(v: Any) -> Optional[float]:
    if v is None:
        return None
    if isinstance(v, float) and pd.isna(v):
        return None
    try:
        if pd.isna(v):
            return None
    except TypeError:
        pass
    return float(v)


def fetch_active_devices_for_schedule(session: Session, as_of: date) -> list[dict[str, Any]]:
    """Return device dicts valid on ``as_of`` (``effective_from`` / ``effective_to`` window)."""
    q = select(DominionDevice).where(
        DominionDevice.effective_from <= as_of,
        or_(DominionDevice.effective_to.is_(None), DominionDevice.effective_to >= as_of),
    )
    rows = session.scalars(q).all()
    return [
        {
            "device_id_external": r.device_id_external,
            "pjm_load_zone_code": r.pjm_load_zone_code,
            "primary_pnode_id": r.primary_pnode_id,
            "primary_pnode_name": r.primary_pnode_name,
            "asset_lat": r.asset_lat,
            "asset_lon": r.asset_lon,
            "asset_display_name": r.asset_display_name,
            "neighbor_pnode_ids": list(r.neighbor_pnode_ids or []),
            "piecewise_curve": r.piecewise_curve,
        }
        for r in rows
    ]


def fetch_hourly_dataframe_for_run(session: Session, ingestion_run_id: int) -> pd.DataFrame:
    """
    Load node hourly rows for one ingestion run (columns compatible with
    ``build_dispatch_schedule`` / ``infer_hourly_frame_columns``).
    """
    q = select(
        DominionDaNodeHourly.pnode_id_external,
        DominionDaNodeHourly.interval_start_utc,
        DominionDaNodeHourly.congestion_price_da,
    ).where(DominionDaNodeHourly.ingestion_run_id == ingestion_run_id)
    return pd.read_sql(q, session.bind)


def persist_dispatch_schedule(
    session: Session,
    ingestion_run_id: int,
    schedule_df: pd.DataFrame,
    *,
    replace_existing: bool = True,
) -> int:
    """
    Insert dispatch schedule rows for ``ingestion_run_id``.

    If ``replace_existing``, deletes prior rows for this run before insert
    (idempotent rebuild of the schedule for that DA snapshot).

    Returns number of rows inserted. Caller commits.
    """
    run = session.get(DominionDaIngestionRun, ingestion_run_id)
    if run is None:
        raise ValueError(f"No dominion_da_ingestion_runs row for id={ingestion_run_id}")

    if schedule_df.empty:
        if replace_existing:
            session.execute(
                delete(DominionDispatchDeviceHour).where(
                    DominionDispatchDeviceHour.ingestion_run_id == ingestion_run_id
                )
            )
        return 0

    if replace_existing:
        session.execute(
            delete(DominionDispatchDeviceHour).where(
                DominionDispatchDeviceHour.ingestion_run_id == ingestion_run_id
            )
        )
        session.flush()

    created_at = datetime.now(timezone.utc)
    mappings: list[dict[str, Any]] = []
    for rec in schedule_df.to_dict("records"):
        ts_utc = schedule_interval_to_utc(rec["interval_start"])
        mappings.append(
            {
                "ingestion_run_id": ingestion_run_id,
                "device_id_external": str(rec["device_id_external"]),
                "pjm_load_zone_code": PJM_ZONE_DOM,
                "primary_pnode_id": str(rec["primary_pnode_id"]),
                "interval_start_utc": ts_utc,
                "raw_congestion": _num_or_none(rec.get("raw_congestion")),
                "resolved_congestion": _num_or_none(rec.get("resolved_congestion")),
                "resolution_strategy": str(rec["resolution_strategy"]),
                "source_pnode_id": (
                    str(rec["source_pnode_id"])
                    if rec.get("source_pnode_id") is not None
                    else None
                ),
                "dispatch_signal": _num_or_none(rec.get("dispatch_signal")),
                "extreme_abs_threshold_usd": _num_or_none(rec.get("extreme_abs_threshold_usd")),
                "period_tier": rec.get("period_tier"),
                "dispatch_mandatory": rec.get("dispatch_mandatory"),
                "dispatch_signal_program": _num_or_none(rec.get("dispatch_signal_program")),
                "created_at_utc": created_at,
            }
        )

    for i in range(0, len(mappings), BATCH):
        session.bulk_insert_mappings(DominionDispatchDeviceHour, mappings[i : i + BATCH])

    logger.info(
        "Persisted %s dominion_dispatch_device_hourly rows for ingestion_run_id=%s",
        len(mappings),
        ingestion_run_id,
    )
    return len(mappings)
