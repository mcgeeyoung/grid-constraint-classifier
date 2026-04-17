"""
Join DA congestion at pnodes with enrolled devices for dispatch planning.

This is a pure DataFrame layer; persistence (Postgres, CSV exports) can wrap it.
"""

from __future__ import annotations

from typing import Iterable

import pandas as pd


def build_device_da_congestion(
    node_lmp_df: pd.DataFrame,
    devices: Iterable[dict],
    *,
    device_id_key: str = "device_id",
    pnode_id_key: str = "pnode_id",
    congestion_col: str = "congestion_price_da",
    time_col: str = "datetime_beginning_ept",
) -> pd.DataFrame:
    """
    For each device with a mapped ``pnode_id``, attach hourly DA congestion.

    ``devices`` entries should be dict-like, e.g.
    ``{"device_id": "DER-001", "pnode_id": 123456}``.

    Rows without a matching ``pnode_id`` / timestamp in ``node_lmp_df`` are dropped.
    """
    dev = pd.DataFrame(list(devices))
    if dev.empty:
        return dev
    if pnode_id_key not in dev.columns:
        raise ValueError(f"devices must include column {pnode_id_key!r}")
    if node_lmp_df.empty:
        return pd.DataFrame()

    left = dev.rename(columns={pnode_id_key: "pnode_id"})
    right = node_lmp_df.copy()
    right["pnode_id"] = right["pnode_id"].astype(str)
    left["pnode_id"] = left["pnode_id"].astype(str)

    merged = left.merge(
        right[[time_col, "pnode_id", congestion_col, "pnode_name"]]
        if "pnode_name" in right.columns
        else right[[time_col, "pnode_id", congestion_col]],
        on="pnode_id",
        how="inner",
    )
    merged = merged.sort_values([device_id_key, time_col]).reset_index(drop=True)
    return merged
