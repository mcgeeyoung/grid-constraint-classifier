"""
Stressed vs extreme periods for Dominion dispatch (optional vs mandatory intensity).

Aligns **stressed** with the classifier-style **|DA congestion| ≥ $/MWh** gate and
**extreme** with a **within-device-day** tail on |congestion| (default 95th percentile),
mirroring the pnode ``extreme_event`` idea relative to the local distribution.
"""

from __future__ import annotations

import logging
from typing import Optional, Set

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

DEFAULT_PEAK_HOURS_EPT = set(range(7, 23))


def interval_hour_ept(interval_start: object) -> int:
    """Hour-of-day 0-23 in **America/New_York** for the interval timestamp.

    `ambiguous=False` picks the standard-time (post-fall-back) reading on
    the one duplicated 01:00 EST hour each year. Wrong on at most one hour
    annually; deterministic and avoids the `"infer"` mode which only works
    on DatetimeIndex (not on a single Timestamp).
    """
    ts = pd.Timestamp(interval_start)
    if ts.tzinfo is None:
        ts = ts.tz_localize(
            "America/New_York",
            ambiguous=False,
            nonexistent="shift_forward",
        )
    else:
        ts = ts.tz_convert("America/New_York")
    return int(ts.hour)


def _extreme_threshold_for_abs_series(abs_series: pd.Series, quantile: float, stressed_floor: float) -> float:
    abs_series = abs_series.dropna()
    if len(abs_series) == 0:
        return float("nan")
    q = float(abs_series.quantile(quantile))
    return max(q, float(stressed_floor))


def apply_period_policy_to_schedule(
    df: pd.DataFrame,
    *,
    enable: bool = True,
    stressed_abs_threshold_usd: float = 2.0,
    extreme_abs_quantile: float = 0.95,
    stressed_signal_fraction: float = 0.5,
    stressed_peak_only: bool = False,
    peak_hours_ept: Optional[Set[int]] = None,
) -> pd.DataFrame:
    """
    Add / overwrite columns:

    - ``extreme_abs_threshold_usd`` — tail threshold for |resolved| that day (per device)
    - ``period_tier`` — ``normal`` | ``stressed`` | ``extreme``
    - ``dispatch_mandatory`` — ``True`` only in **extreme** hours with valid congestion
    - ``dispatch_signal_program`` — **0** in normal; **scaled** piecewise signal in stressed
      (optional dispatch); **full** ``dispatch_signal`` in extreme (mandatory)

    When ``enable`` is False, tiers are ``off``, ``dispatch_mandatory`` is False, and
    ``dispatch_signal_program`` equals ``dispatch_signal`` (no gating).
    """
    if df.empty:
        return df

    out = df.copy()
    peak = peak_hours_ept if peak_hours_ept is not None else DEFAULT_PEAK_HOURS_EPT

    if not enable:
        out["extreme_abs_threshold_usd"] = np.nan
        out["period_tier"] = "off"
        out["dispatch_mandatory"] = False
        out["dispatch_signal_program"] = out["dispatch_signal"]
        return out

    out["extreme_abs_threshold_usd"] = np.nan
    for _, idx in out.groupby("device_id_external").groups.items():
        sub = out.loc[idx]
        abs_r = sub["resolved_congestion"].abs()
        thr = _extreme_threshold_for_abs_series(abs_r, extreme_abs_quantile, stressed_abs_threshold_usd)
        out.loc[idx, "extreme_abs_threshold_usd"] = thr

    tiers: list[str] = []
    mandatory: list[bool] = []
    prog: list[float] = []

    for _, row in out.iterrows():
        sig = row.get("dispatch_signal", float("nan"))
        res = row.get("resolved_congestion")
        ext_thr = row.get("extreme_abs_threshold_usd", float("nan"))
        ts = row["interval_start"]

        if res is None or pd.isna(res):
            tiers.append("normal")
            mandatory.append(False)
            prog.append(0.0)
            continue

        ab = abs(float(res))
        if ext_thr is None or pd.isna(ext_thr):
            ext_thr = stressed_abs_threshold_usd

        hour = interval_hour_ept(ts)
        in_peak = hour in peak

        if ab >= float(ext_thr):
            tiers.append("extreme")
            mandatory.append(True)
            if sig is None or pd.isna(sig):
                prog.append(0.0)
            else:
                prog.append(float(sig))
            continue

        if ab >= stressed_abs_threshold_usd:
            if stressed_peak_only and not in_peak:
                tiers.append("normal")
                mandatory.append(False)
                prog.append(0.0)
                continue
            tiers.append("stressed")
            mandatory.append(False)
            if sig is None or pd.isna(sig):
                prog.append(0.0)
            else:
                prog.append(float(sig) * float(stressed_signal_fraction))
            continue

        tiers.append("normal")
        mandatory.append(False)
        prog.append(0.0)

    out["period_tier"] = tiers
    out["dispatch_mandatory"] = mandatory
    out["dispatch_signal_program"] = prog

    n_ext = sum(1 for t in tiers if t == "extreme")
    n_str = sum(1 for t in tiers if t == "stressed")
    logger.info(
        "period policy: extreme=%s stressed=%s (threshold $%.2f, q=%.2f, peak_stressed_only=%s)",
        n_ext,
        n_str,
        stressed_abs_threshold_usd,
        extreme_abs_quantile,
        stressed_peak_only,
    )
    return out
