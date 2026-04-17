"""
Fetch PJM day-ahead hourly node LMPs for zone DOM, including congestion_price_da.

Designed for a daily job after DA clears: pass a single operating date (or small
range) instead of full-year pulls used by the classifier pipeline.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import TYPE_CHECKING, Optional

import pandas as pd

from dominion_dispatch.config import DEFAULT_DA_NODE_LMP_TYPE, PJM_ZONE_DOM

if TYPE_CHECKING:
    from src.pjm_client import PJMClient

logger = logging.getLogger(__name__)


def _pjm_date_range_ept(day: date, end_day_inclusive: Optional[date] = None) -> str:
    """Build PJM ``datetime_beginning_ept`` range for one or more local calendar days (EPT)."""
    if end_day_inclusive is None:
        end_day_inclusive = day
    start = f"{day.month}/{day.day}/{day.year} 00:00"
    end = f"{end_day_inclusive.month}/{end_day_inclusive.day}/{end_day_inclusive.year} 23:00"
    return f"{start}to{end}"


def fetch_da_node_congestion_dom(
    client: PJMClient,
    operating_day: date,
    *,
    operating_day_end: Optional[date] = None,
    lmp_type: str = DEFAULT_DA_NODE_LMP_TYPE,
    zone: str = PJM_ZONE_DOM,
) -> pd.DataFrame:
    """
    Return DA hourly rows for all nodes in ``zone`` with congestion components.

    Columns depend on PJM response; typical node pull includes
    ``datetime_beginning_ept``, ``pnode_id``, ``pnode_name``,
    ``congestion_price_da``, ``total_lmp_da``, ``marginal_loss_price_da``.
    """
    date_range = _pjm_date_range_ept(operating_day, operating_day_end)
    logger.info(
        "Fetching DA node LMPs zone=%s type=%s range=%s",
        zone,
        lmp_type,
        date_range,
    )
    df = client.query_lmps(
        datetime_beginning_ept=date_range,
        lmp_type=lmp_type,
        zone=zone,
    )
    if df.empty:
        return df

    if "datetime_beginning_ept" in df.columns:
        df["datetime_beginning_ept"] = pd.to_datetime(df["datetime_beginning_ept"])
    for col in ("total_lmp_da", "congestion_price_da", "marginal_loss_price_da"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def filter_to_pnodes(df: pd.DataFrame, pnode_ids: set[int] | set[str]) -> pd.DataFrame:
    """Restrict a node LMP dataframe to an explicit allowlist of ``pnode_id`` values."""
    if df.empty or "pnode_id" not in df.columns:
        return df
    ids = {str(x) for x in pnode_ids}
    s = df["pnode_id"].astype(str)
    return df.loc[s.isin(ids)].copy()
