"""
Persist PJM DA node hourly rows + ingestion metadata to Postgres.

Idempotency: ``idempotency_key`` is deterministic per
(``data_source``, ``zone_code``, ``lmp_type``, ``operating_date``).
A successful run is skipped on re-entry unless ``replace_existing`` is True
(in which case the prior run and its hourly rows are removed first).
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Optional

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.dominion_der import DominionDaIngestionRun, DominionDaNodeHourly
from dominion_dispatch.da_congestion import _pjm_date_range_ept

logger = logging.getLogger(__name__)

BATCH = 4000


def build_idempotency_key(
    *,
    data_source: str = "pjm_da_hrl_lmps",
    zone_code: str,
    lmp_type: str,
    operating_date: date,
) -> str:
    return f"{data_source}|{zone_code}|{lmp_type}|{operating_date.isoformat()}"


def _ept_naive_to_utc(series: pd.Series) -> pd.Series:
    ts = pd.to_datetime(series)
    if ts.dt.tz is not None:
        return ts.dt.tz_convert("UTC")
    localized = ts.dt.tz_localize(
        "America/New_York",
        ambiguous="infer",
        nonexistent="shift_forward",
    )
    return localized.dt.tz_convert("UTC")


def _prepare_hourly_frame(
    df: pd.DataFrame,
    *,
    operating_date: date,
    zone_code: str,
    lmp_type: str,
) -> pd.DataFrame:
    """Translate the canonical ISODriver schema to DB-row shape.

    Reads canonical columns produced by `PJMDriver.fetch_da_hourly`:
        pnode_id_external, pnode_name, hour_ending_ept,
        lmp_da, energy_price_da, congestion_price_da, loss_price_da

    Computes `interval_start_utc` as `hour_ending_ept - 1h` localized
    America/New_York then converted to UTC. The DB stores hour-beginning
    UTC; the canonical schema uses hour-ending naive EPT (per the
    ISODriver protocol).
    """
    if df.empty:
        return df
    out = df.copy()
    if "hour_ending_ept" not in out.columns:
        raise ValueError("DataFrame must include hour_ending_ept (canonical schema)")
    if "pnode_id_external" not in out.columns:
        raise ValueError("DataFrame must include pnode_id_external (canonical schema)")

    # HE (canonical) -> HB (DB) -> UTC.
    he_ept = pd.to_datetime(out["hour_ending_ept"])
    hb_ept = he_ept - pd.Timedelta(hours=1)
    out["interval_start_utc"] = _ept_naive_to_utc(hb_ept)

    out["pnode_id_external"] = out["pnode_id_external"].astype(str)
    out["operating_date"] = operating_date
    out["zone_code"] = zone_code
    out["lmp_type"] = lmp_type
    return out.drop_duplicates(subset=["pnode_id_external", "interval_start_utc"], keep="first")


def ingest_da_dom_dataframe(
    session: Session,
    df: pd.DataFrame,
    operating_date: date,
    *,
    zone_code: str,
    lmp_type: str,
    retrieved_at_utc: Optional[datetime] = None,
    replace_existing: bool = False,
    data_source: str = "pjm_da_hrl_lmps",
) -> DominionDaIngestionRun:
    """
    Insert a new ingestion run and hourly rows. Commits are the caller's responsibility.

    Returns the ``DominionDaIngestionRun`` row (success or failed status).
    """
    if retrieved_at_utc is None:
        retrieved_at_utc = datetime.now(timezone.utc)

    idem = build_idempotency_key(
        data_source=data_source,
        zone_code=zone_code,
        lmp_type=lmp_type,
        operating_date=operating_date,
    )

    existing = session.scalar(
        select(DominionDaIngestionRun).where(DominionDaIngestionRun.idempotency_key == idem)
    )
    if existing is not None:
        if existing.status == "success" and not replace_existing:
            logger.info("Skip ingest: already success for %s", idem)
            return existing
        session.delete(existing)
        session.flush()

    query_range = _pjm_date_range_ept(operating_date, operating_date)
    run = DominionDaIngestionRun(
        idempotency_key=idem,
        operating_date=operating_date,
        zone_code=zone_code,
        lmp_type=lmp_type,
        data_source=data_source,
        status="pending",
        retrieved_at_utc=retrieved_at_utc,
        request_started_at_utc=datetime.now(timezone.utc),
        query_date_range=query_range,
    )
    session.add(run)
    session.flush()

    if df.empty:
        run.status = "success"
        run.row_count = 0
        run.request_completed_at_utc = datetime.now(timezone.utc)
        return run

    try:
        prepared = _prepare_hourly_frame(
            df, operating_date=operating_date, zone_code=zone_code, lmp_type=lmp_type
        )
    except Exception as e:
        run.status = "failed"
        run.error_message = str(e)
        run.request_completed_at_utc = datetime.now(timezone.utc)
        return run

    mappings: list[dict] = []
    for rec in prepared.to_dict("records"):
        ts = rec["interval_start_utc"]
        if hasattr(ts, "to_pydatetime"):
            ts = ts.to_pydatetime()
        # DB column names (`total_lmp_da`, `system_energy_price_da`,
        # `marginal_loss_price_da`) are PJM-native; map from the canonical
        # column names emitted by PJMDriver. `congestion_price_da` and
        # `pnode_name` are the same in both schemas.
        mappings.append(
            {
                "ingestion_run_id": run.id,
                "operating_date": operating_date,
                "zone_code": zone_code,
                "lmp_type": lmp_type,
                "interval_start_utc": ts,
                "pnode_id_external": rec["pnode_id_external"],
                "pnode_name": rec.get("pnode_name"),
                "congestion_price_da": _num(rec.get("congestion_price_da")),
                "total_lmp_da": _num(rec.get("lmp_da")),
                "marginal_loss_price_da": _num(rec.get("loss_price_da")),
                "system_energy_price_da": _num(rec.get("energy_price_da")),
            }
        )

    for i in range(0, len(mappings), BATCH):
        session.bulk_insert_mappings(DominionDaNodeHourly, mappings[i : i + BATCH])

    run.status = "success"
    run.row_count = len(mappings)
    run.request_completed_at_utc = datetime.now(timezone.utc)
    return run


def _num(v) -> Optional[float]:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    return float(v)
