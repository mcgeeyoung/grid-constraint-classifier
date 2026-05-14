"""
Join DA congestion at pnodes with enrolled devices for dispatch planning.

This is a pure DataFrame layer; persistence (Postgres, CSV exports) can wrap it.
"""

from __future__ import annotations

from typing import Iterable, Optional

import pandas as pd


def build_device_da_congestion(
    node_lmp_df: pd.DataFrame,
    devices: Iterable[dict],
    *,
    device_id_key: str = "device_id",
    pnode_id_key: str = "pnode_id",
    congestion_col: str = "congestion_price_da",
    time_col: Optional[str] = None,
    node_pnode_col: Optional[str] = None,
) -> pd.DataFrame:
    """
    For each device with a mapped pnode id, attach hourly DA congestion.

    ``devices`` entries should be dict-like, e.g.
    ``{"device_id": "DER-001", "pnode_id": 123456}``.

    `node_lmp_df` may use either the canonical ISODriver schema
    (`pnode_id_external`, `hour_ending_ept`) or the legacy PJM-native /
    DB-export schema (`pnode_id`, `datetime_beginning_ept` /
    `interval_start_utc`). The columns are auto-detected when
    `time_col` / `node_pnode_col` are unspecified.

    Rows without a matching pnode / timestamp in `node_lmp_df` are dropped.
    """
    dev = pd.DataFrame(list(devices))
    if dev.empty:
        return dev
    if pnode_id_key not in dev.columns:
        raise ValueError(f"devices must include column {pnode_id_key!r}")
    if node_lmp_df.empty:
        return pd.DataFrame()

    if node_pnode_col is None:
        for cand in ("pnode_id_external", "pnode_id"):
            if cand in node_lmp_df.columns:
                node_pnode_col = cand
                break
        if node_pnode_col is None:
            raise ValueError(
                "node_lmp_df needs pnode_id_external (canonical) or pnode_id (legacy)"
            )

    if time_col is None:
        for cand in ("hour_ending_ept", "interval_start_utc", "datetime_beginning_ept"):
            if cand in node_lmp_df.columns:
                time_col = cand
                break
        if time_col is None:
            raise ValueError(
                "node_lmp_df needs hour_ending_ept (canonical), "
                "interval_start_utc (DB export), or datetime_beginning_ept (legacy PJM)"
            )

    left = dev.rename(columns={pnode_id_key: "_pnode_join"})
    right = node_lmp_df.rename(columns={node_pnode_col: "_pnode_join"}).copy()
    right["_pnode_join"] = right["_pnode_join"].astype(str)
    left["_pnode_join"] = left["_pnode_join"].astype(str)

    cols = [time_col, "_pnode_join", congestion_col]
    if "pnode_name" in right.columns:
        cols.append("pnode_name")

    merged = left.merge(right[cols], on="_pnode_join", how="inner")
    merged = merged.rename(columns={"_pnode_join": "pnode_id"})
    merged = merged.sort_values([device_id_key, time_col]).reset_index(drop=True)
    return merged
