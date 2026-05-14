"""
Fetch PJM day-ahead hourly node LMPs for zone DOM via the ISO driver protocol.

Routes through `isos.pjm.driver.PJMDriver`, so this module no longer talks to
the PJM HTTP client directly. The returned DataFrame uses the canonical
ISODriver schema (`pnode_id_external`, `pnode_name`, `hour_ending_ept`,
`lmp_da`, `energy_price_da`, `congestion_price_da`, `loss_price_da`); the
`_prepare_hourly_frame` step in `persist.py` renames to the DB column
names at the write boundary.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import TYPE_CHECKING, Optional

import pandas as pd

from dominion_dispatch.config import DEFAULT_DA_NODE_LMP_TYPE, PJM_ZONE_DOM

if TYPE_CHECKING:
    from isos.pjm.driver import PJMDriver

logger = logging.getLogger(__name__)


def _pjm_date_range_ept(day: date, end_day_inclusive: Optional[date] = None) -> str:
    """Build PJM ``datetime_beginning_ept`` range for one or more local calendar days (EPT).

    Kept as a public helper because `persist.py` writes this string into
    `DominionDaIngestionRun.query_date_range` for traceability.
    """
    if end_day_inclusive is None:
        end_day_inclusive = day
    start = f"{day.month}/{day.day}/{day.year} 00:00"
    end = f"{end_day_inclusive.month}/{end_day_inclusive.day}/{end_day_inclusive.year} 23:00"
    return f"{start}to{end}"


def fetch_da_node_congestion_dom(
    driver: "PJMDriver",
    operating_day: date,
    *,
    operating_day_end: Optional[date] = None,
    lmp_type: str = DEFAULT_DA_NODE_LMP_TYPE,
    zone: str = PJM_ZONE_DOM,
) -> pd.DataFrame:
    """Return DA hourly rows for all LOAD pnodes in `zone` for one or more operating days.

    Output schema (canonical ISODriver shape):
        pnode_id_external, pnode_name, hour_ending_ept,
        lmp_da, energy_price_da, congestion_price_da, loss_price_da

    Multi-day pulls loop the driver per day. The PJM client's rate limiter
    paces inter-day requests automatically; expect ~10s per day.

    Raises ValueError on non-LOAD `lmp_type` -- the ISO driver protocol
    contract is LOAD-typed pnodes; the legacy direct-client path supported
    other types but no current consumer uses them.
    """
    if lmp_type.upper() != "LOAD":
        raise ValueError(
            f"fetch_da_node_congestion_dom now routes through PJMDriver, which "
            f"is LOAD-only per the ISODriver protocol. Got lmp_type={lmp_type!r}. "
            f"For GEN / AGGREGATE / ZONE pulls, call PJMClient.query_lmps directly."
        )

    end = operating_day_end or operating_day
    if end < operating_day:
        raise ValueError(
            f"operating_day_end ({end}) is before operating_day ({operating_day})"
        )

    days = []
    cur = operating_day
    while cur <= end:
        days.append(cur)
        cur += timedelta(days=1)

    logger.info(
        "Fetching DA node LMPs zone=%s lmp_type=%s days=%d (%s..%s) via PJMDriver",
        zone, lmp_type, len(days), operating_day.isoformat(), end.isoformat(),
    )

    frames: list[pd.DataFrame] = []
    for d in days:
        df = driver.fetch_da_hourly(d, zone)
        if not df.empty:
            frames.append(df)

    if not frames:
        # Stable empty canonical frame for downstream callers.
        from isos.pjm.driver import OUTPUT_COLUMNS  # local import to avoid cycle
        return pd.DataFrame(columns=OUTPUT_COLUMNS)

    return pd.concat(frames, ignore_index=True)


def filter_to_pnodes(df: pd.DataFrame, pnode_ids: set[int] | set[str]) -> pd.DataFrame:
    """Restrict a node LMP dataframe to an explicit allowlist of pnode ids.

    Accepts either canonical (`pnode_id_external`) or legacy PJM-native
    (`pnode_id`) column names so DB exports also work.
    """
    if df.empty:
        return df
    pid_col = (
        "pnode_id_external" if "pnode_id_external" in df.columns
        else "pnode_id" if "pnode_id" in df.columns
        else None
    )
    if pid_col is None:
        return df
    ids = {str(x) for x in pnode_ids}
    s = df[pid_col].astype(str)
    return df.loc[s.isin(ids)].copy()
