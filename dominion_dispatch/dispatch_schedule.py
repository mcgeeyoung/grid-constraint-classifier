"""
Build a per-device, per-hour dispatch table from DA congestion and enrollment rules.
"""

from __future__ import annotations

import logging
from typing import Any, Iterable, Mapping, Optional, Set

import pandas as pd

from dominion_dispatch.config import (
    DISPATCH_EXTREME_ABS_QUANTILE_DEFAULT,
    DISPATCH_STRESSED_ABS_USD_DEFAULT,
    DISPATCH_STRESSED_SIGNAL_FRACTION_DEFAULT,
    PJM_ZONE_DOM,
)
from dominion_dispatch.period_dispatch import apply_period_policy_to_schedule
from dominion_dispatch.signal_engine import (
    build_hourly_congestion_lookup,
    congestion_at_node_hour,
    piecewise_signal,
    resolve_congestion_with_neighbors,
)

logger = logging.getLogger(__name__)

SCHEDULE_OUT_COLUMNS = [
    "device_id_external",
    "pjm_load_zone_code",
    "primary_pnode_id",
    "interval_start",
    "raw_congestion",
    "resolved_congestion",
    "resolution_strategy",
    "source_pnode_id",
    "dispatch_signal",
    "extreme_abs_threshold_usd",
    "period_tier",
    "dispatch_mandatory",
    "dispatch_signal_program",
]


def infer_hourly_frame_columns(
    df: pd.DataFrame, *, congestion_col: str = "congestion_price_da"
) -> tuple[str, str, str]:
    """
    Detect (pnode_col, time_col, congestion_col) for PJM pulls vs Postgres hourly exports.

    Raises ``ValueError`` if required columns cannot be inferred.
    """
    if congestion_col not in df.columns:
        raise ValueError(f"hourly_df must include {congestion_col!r}")

    if "pnode_id_external" in df.columns:
        pnode_col = "pnode_id_external"
    elif "pnode_id" in df.columns:
        pnode_col = "pnode_id"
    else:
        raise ValueError("hourly_df needs pnode_id or pnode_id_external")

    if "interval_start_utc" in df.columns:
        time_col = "interval_start_utc"
    elif "datetime_beginning_ept" in df.columns:
        time_col = "datetime_beginning_ept"
    else:
        raise ValueError("hourly_df needs interval_start_utc or datetime_beginning_ept")

    return pnode_col, time_col, congestion_col


def _normalize_device(row: Mapping[str, Any]) -> dict[str, Any]:
    """Map flexible keys to device id, DOM settlement zone, pnode, neighbors, curve."""
    dev_id = row.get("device_id_external") or row.get("device_id")
    if dev_id is None:
        raise ValueError("each device needs device_id_external or device_id")
    primary = row.get("primary_pnode_id") or row.get("pnode_id")
    if primary is None:
        raise ValueError("each device needs primary_pnode_id or pnode_id")
    # Dominion DER program: settlement geography is always PJM **DOM**.
    zone = PJM_ZONE_DOM
    neighbors = row.get("neighbor_pnode_ids") or row.get("neighbors") or []
    if neighbors is None:
        neighbors = []
    if not isinstance(neighbors, (list, tuple)):
        neighbors = list(neighbors) if neighbors else []
    curve = row.get("piecewise_curve") or row.get("piecewise")
    return {
        "device_id_external": str(dev_id),
        "pjm_load_zone_code": zone,
        "primary_pnode_id": str(primary),
        "neighbor_pnode_ids": [str(x) for x in neighbors],
        "piecewise_curve": curve if isinstance(curve, list) else None,
    }


def build_dispatch_schedule(
    devices: Iterable[Mapping[str, Any]],
    hourly_df: pd.DataFrame,
    *,
    pnode_col: Optional[str] = None,
    time_col: Optional[str] = None,
    congestion_col: Optional[str] = None,
    enable_period_policy: bool = True,
    stressed_abs_threshold_usd: float = DISPATCH_STRESSED_ABS_USD_DEFAULT,
    extreme_abs_quantile: float = DISPATCH_EXTREME_ABS_QUANTILE_DEFAULT,
    stressed_signal_fraction: float = DISPATCH_STRESSED_SIGNAL_FRACTION_DEFAULT,
    stressed_peak_only: bool = False,
    peak_hours_ept: Optional[Set[int]] = None,
) -> pd.DataFrame:
    """
    One row per (device, hour): primary-only congestion, neighbor-resolved congestion,
    resolution strategy, and piecewise dispatch signal.

    **Columns output**

    - ``device_id_external``, ``pjm_load_zone_code`` (always **DOM** for this program)
    - ``primary_pnode_id``
    - ``interval_start`` — same values as the detected time column (naive EPT or UTC-aware)
    - ``raw_congestion`` — DA congestion at the **primary** pnode only (null if missing)
    - ``resolved_congestion`` — after **neighbor** fallback (null if still missing)
    - ``resolution_strategy`` — ``primary``, ``neighbor:<pnode>``, or ``missing``
    - ``source_pnode_id`` — pnode that supplied ``resolved_congestion``
    - ``dispatch_signal`` — ``piecewise_signal(resolved_congestion, piecewise_curve)``
      (null when ``resolved_congestion`` is null; pass-through congestion when curve is empty)

    **Period policy** (when ``enable_period_policy``): ``period_tier`` is ``normal``,
    ``stressed``, or ``extreme``. **Stressed** = \|resolved\| ≥ ``stressed_abs_threshold_usd``
    (default **$2/MWh**, same spirit as ``core/constraint_classifier``). **Extreme** =
    \|resolved\| ≥ per-device-day quantile of \|resolved\| (default **P95**), floored at the
    stressed threshold (same spirit as ``core/pnode_analyzer`` tail hours). **Optional**
    stressed dispatch scales ``dispatch_signal`` by ``stressed_signal_fraction``;
    **mandatory** extreme uses full ``dispatch_signal``. ``dispatch_signal_program`` is the
    gated intensity; ``dispatch_mandatory`` is True only in extreme hours.

    ``devices`` entries may use keys aligned with ``DominionDevice`` or minimal
    ``{"device_id": "...", "pnode_id": "...", ...}``. Settlement load zone is always **DOM**.
    """
    if hourly_df.empty:
        return pd.DataFrame(columns=list(SCHEDULE_OUT_COLUMNS))

    if pnode_col is None or time_col is None or congestion_col is None:
        inferred_p, inferred_t, inferred_c = infer_hourly_frame_columns(
            hourly_df,
            congestion_col=congestion_col or "congestion_price_da",
        )
        pnode_col = pnode_col or inferred_p
        time_col = time_col or inferred_t
        congestion_col = congestion_col or inferred_c

    lookup = build_hourly_congestion_lookup(
        hourly_df,
        pnode_col=pnode_col,
        time_col=time_col,
        congestion_col=congestion_col,
    )
    unique_times = sorted(hourly_df[time_col].dropna().unique())
    device_list = [_normalize_device(d) for d in devices]
    if not device_list:
        return pd.DataFrame(columns=list(SCHEDULE_OUT_COLUMNS))

    rows: list[dict[str, Any]] = []
    for dev in device_list:
        primary = dev["primary_pnode_id"]
        zone_code = dev["pjm_load_zone_code"]
        neighbors = dev["neighbor_pnode_ids"]
        curve = dev["piecewise_curve"]
        for ts in unique_times:
            raw_val = congestion_at_node_hour(lookup, primary, ts)

            res = resolve_congestion_with_neighbors(lookup, ts, primary, neighbors)
            resolved = res.congestion
            strategy = res.strategy
            source_pid = res.source_pnode_id

            if resolved is None:
                sig: Any = float("nan")
            else:
                sig = piecewise_signal(resolved, curve)

            rows.append(
                {
                    "device_id_external": dev["device_id_external"],
                    "pjm_load_zone_code": zone_code,
                    "primary_pnode_id": primary,
                    "interval_start": ts,
                    "raw_congestion": raw_val,
                    "resolved_congestion": resolved,
                    "resolution_strategy": strategy,
                    "source_pnode_id": source_pid,
                    "dispatch_signal": sig,
                }
            )

    if not rows:
        return pd.DataFrame(columns=list(SCHEDULE_OUT_COLUMNS))

    out = pd.DataFrame(rows)
    out = apply_period_policy_to_schedule(
        out,
        enable=enable_period_policy,
        stressed_abs_threshold_usd=stressed_abs_threshold_usd,
        extreme_abs_quantile=extreme_abs_quantile,
        stressed_signal_fraction=stressed_signal_fraction,
        stressed_peak_only=stressed_peak_only,
        peak_hours_ept=peak_hours_ept,
    )
    logger.info("dispatch schedule: %s device-hours", len(out))
    return out
