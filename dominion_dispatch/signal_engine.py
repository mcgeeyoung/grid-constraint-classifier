"""
Dispatch signal helpers: piecewise mapping of DA congestion and neighbor-pnode fallback.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Optional

import pandas as pd


@dataclass(frozen=True)
class CongestionResolution:
    """Which pnode supplied the congestion value used for dispatch."""

    congestion: Optional[float]
    source_pnode_id: Optional[str]
    strategy: str  # primary | neighbor:N | missing


def piecewise_signal(raw_congestion: float, knots: Optional[list[dict[str, Any]]]) -> float:
    """
    Piecewise-linear map from PJM DA congestion ($/MWh) to a bounded dispatch signal.

    ``knots`` is a list of ``{"congestion": float, "signal": float}``, sorted by
    congestion ascending in storage; this function sorts defensively.
    Outside the knot range, the signal is **flat-clamped** to the nearest endpoint.
    If ``knots`` is None or empty, returns ``raw_congestion`` unchanged (pass-through).
    """
    if not knots:
        return float(raw_congestion)

    ordered = sorted(
        ((float(k["congestion"]), float(k["signal"])) for k in knots),
        key=lambda t: t[0],
    )
    xs = [t[0] for t in ordered]
    ys = [t[1] for t in ordered]
    x = float(raw_congestion)
    if x <= xs[0]:
        return ys[0]
    if x >= xs[-1]:
        return ys[-1]
    for i in range(len(xs) - 1):
        if xs[i] <= x <= xs[i + 1]:
            x0, x1 = xs[i], xs[i + 1]
            y0, y1 = ys[i], ys[i + 1]
            if x1 == x0:
                return y1
            t = (x - x0) / (x1 - x0)
            return y0 + t * (y1 - y0)
    return ys[-1]


def congestion_at_node_hour(
    lookup: pd.Series,
    pnode_id: str,
    ts_key: Any,
) -> Optional[float]:
    """Return DA congestion at (``pnode_id``, ``ts_key``) or None if absent."""
    return _lookup_congestion(lookup, pnode_id, ts_key)


def _lookup_congestion(
    lookup: pd.Series,
    pnode_id: str,
    ts_key: Any,
) -> Optional[float]:
    key = (str(pnode_id), ts_key)
    if key not in lookup.index:
        return None
    val = lookup.loc[key]
    if isinstance(val, pd.Series):
        val = val.iloc[0]
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    return float(val)


def build_hourly_congestion_lookup(
    df: pd.DataFrame,
    *,
    pnode_col: str = "pnode_id",
    time_col: str = "datetime_beginning_ept",
    congestion_col: str = "congestion_price_da",
) -> pd.Series:
    """
    Multi-index Series (pnode_id, timestamp) -> congestion.

    For Postgres-exported hourly frames, pass ``pnode_col='pnode_id_external'`` and
    ``time_col='interval_start_utc'``.
    """
    d = df[[pnode_col, time_col, congestion_col]].copy()
    d[pnode_col] = d[pnode_col].astype(str)
    d = d.drop_duplicates(subset=[pnode_col, time_col], keep="first")
    return d.set_index([pnode_col, time_col])[congestion_col]


def resolve_congestion_with_neighbors(
    lookup: pd.Series,
    interval_start_utc: Any,
    primary_pnode_id: str,
    neighbor_pnode_ids: Optional[Iterable[str]] = None,
) -> CongestionResolution:
    """
    Use primary pnode congestion if present; otherwise try neighbors in order.
    """
    primary = _lookup_congestion(lookup, str(primary_pnode_id), interval_start_utc)
    if primary is not None:
        return CongestionResolution(primary, str(primary_pnode_id), "primary")
    for nid in neighbor_pnode_ids or ():
        v = _lookup_congestion(lookup, str(nid), interval_start_utc)
        if v is not None:
            return CongestionResolution(v, str(nid), f"neighbor:{nid}")
    return CongestionResolution(None, None, "missing")
