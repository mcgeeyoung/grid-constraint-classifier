"""
Grid constraint classifier using LMP decomposition.

Classifies zones by constraint type:
  - "transmission": congestion-dominated (flow limits on transmission lines)
  - "generation": energy-price-dominated (insufficient local generation)
  - "both": significant transmission AND generation constraints
  - "unconstrained": minimal constraints of either type

Uses congestion and energy price components from day-ahead hourly LMPs
to compute per-zone scoring metrics.

ISO-agnostic: works with any ISO's LMP data once column names are
normalized to the canonical format (or PJM column names by default).
"""

import logging
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ── Tunable thresholds ──

# Transmission constraint indicators (congestion-based)
CONGESTION_RATIO_WEIGHT = 0.30      # abs(congestion) / total_lmp
CONGESTION_VOLATILITY_WEIGHT = 0.25 # Std dev of congestion prices
CONGESTION_HOURS_PCT_WEIGHT = 0.25  # % hours with |congestion| > threshold
PEAK_OFFPEAK_RATIO_WEIGHT = 0.20   # Peak/off-peak congestion ratio

# Generation constraint indicators (energy-price-based)
ENERGY_DEVIATION_WEIGHT = 0.35     # Zone energy vs system energy deviation
ENERGY_VOLATILITY_WEIGHT = 0.30   # Energy price volatility
LOSS_COMPONENT_WEIGHT = 0.20      # Marginal loss (proxy for remote generation)
ENERGY_HOURS_PCT_WEIGHT = 0.15    # % hours with energy > system avg + threshold

# Classification thresholds
CLASSIFICATION_THRESHOLD = 0.5    # Score above this = constrained
CONGESTION_THRESHOLD_DOLLARS = 2.0  # $/MWh to count as "congested hour"
ENERGY_DEVIATION_THRESHOLD = 3.0    # $/MWh above system avg = "high energy"

# Default peak hours: HE 7-22 (EPT), matching PJM peak period
DEFAULT_PEAK_HOURS = set(range(7, 23))

# ── Column name mapping ──
# Maps canonical names to actual DataFrame column names.
# Adapters normalize ISO-specific columns to canonical names;
# these defaults match PJM Data Miner 2 output for backward compat.
DEFAULT_COLUMNS = {
    "timestamp": "datetime_beginning_ept",
    "zone": "pnode_name",
    "lmp": "total_lmp_da",
    "congestion": "congestion_price_da",
    "loss": "marginal_loss_price_da",
    "energy": "system_energy_price_da",
    "hour": "hour",
}


def compute_zone_metrics(
    df: pd.DataFrame,
    peak_hours: Optional[set[int]] = None,
    rto_aggregates: Optional[set[str]] = None,
    columns: Optional[dict[str, str]] = None,
) -> pd.DataFrame:
    """
    Compute per-zone constraint metrics from hourly LMP data.

    Args:
        df: LMP DataFrame with zone-level hourly data.
        peak_hours: Set of hours considered peak (default: 7-22).
        rto_aggregates: Zone names to exclude (e.g. RTO-level aggregates).
            Defaults to empty set. Pass {"PJM-RTO", "MID-ATL/APS"} for PJM.
        columns: Column name mapping (canonical -> actual). Defaults to
            PJM column names for backward compatibility.

    Returns:
        DataFrame with one row per zone and metric columns.
    """
    if peak_hours is None:
        peak_hours = DEFAULT_PEAK_HOURS
    if rto_aggregates is None:
        rto_aggregates = set()
    col = {**DEFAULT_COLUMNS, **(columns or {})}

    zone_col = col["zone"]
    lmp_col = col["lmp"]
    cong_col = col["congestion"]
    loss_col = col["loss"]
    energy_col = col["energy"]
    hour_col = col["hour"]
    ts_col = col["timestamp"]

    # Exclude RTO-level aggregates
    if rto_aggregates:
        zone_df = df[~df[zone_col].isin(rto_aggregates)].copy()
    else:
        zone_df = df.copy()

    # Mark peak/off-peak
    zone_df["is_peak"] = zone_df[hour_col].isin(peak_hours)

    # System average energy price per hour
    sys_energy = zone_df.groupby(ts_col)[energy_col].mean()

    metrics = []

    for zone_name, zdf in zone_df.groupby(zone_col):
        n_hours = len(zdf)
        if n_hours < 100:  # Skip zones with insufficient data
            continue

        cong = zdf[cong_col]
        lmp = zdf[lmp_col]
        energy = zdf[energy_col]
        loss = zdf[loss_col]

        # ── Transmission metrics ──

        # 1. Congestion ratio: mean(|congestion|) / mean(|lmp|)
        congestion_ratio = cong.abs().mean() / max(lmp.abs().mean(), 0.01)

        # 2. Congestion volatility (CV = std/mean, normalized)
        cong_std = cong.std()
        cong_cv = cong_std / max(cong.abs().mean(), 0.01)

        # 3. Congested hours percentage
        congested_hours_pct = (cong.abs() > CONGESTION_THRESHOLD_DOLLARS).mean()

        # 4. Peak/off-peak congestion ratio
        peak_cong = zdf[zdf["is_peak"]][cong_col].abs().mean()
        offpeak_cong = zdf[~zdf["is_peak"]][cong_col].abs().mean()
        peak_offpeak_ratio = peak_cong / max(offpeak_cong, 0.01)

        # ── Generation metrics ──

        # 5. Energy price deviation from system average
        zone_hours = zdf.set_index(ts_col)
        merged = zone_hours.join(sys_energy, rsuffix="_sys")
        sys_col_name = f"{energy_col}_sys"
        if sys_col_name in merged.columns:
            energy_dev = (merged[energy_col] - merged[sys_col_name]).abs().mean()
        else:
            energy_dev = 0

        # 6. Energy price volatility
        energy_vol = energy.std() / max(energy.mean(), 0.01)

        # 7. Marginal loss component (high loss = remote from generation)
        avg_loss = loss.abs().mean()
        loss_ratio = avg_loss / max(lmp.abs().mean(), 0.01)

        # 8. High-energy hours percentage
        high_energy_pct = (energy > energy.mean() + ENERGY_DEVIATION_THRESHOLD).mean()

        # ── Raw stats for output ──
        avg_congestion = cong.mean()
        avg_abs_congestion = cong.abs().mean()
        avg_lmp = lmp.mean()
        max_congestion = cong.abs().max()

        metrics.append({
            "zone": zone_name,
            "n_hours": n_hours,
            # Transmission metrics
            "congestion_ratio": congestion_ratio,
            "congestion_volatility": min(cong_cv, 10),  # Cap outliers
            "congested_hours_pct": congested_hours_pct,
            "peak_offpeak_ratio": min(peak_offpeak_ratio, 10),
            # Generation metrics
            "energy_deviation": energy_dev,
            "energy_volatility": min(energy_vol, 10),
            "loss_ratio": loss_ratio,
            "high_energy_pct": high_energy_pct,
            # Raw stats
            "avg_congestion": avg_congestion,
            "avg_abs_congestion": avg_abs_congestion,
            "avg_lmp": avg_lmp,
            "max_congestion": max_congestion,
            "congestion_std": cong_std,
        })

    return pd.DataFrame(metrics)


def _normalize_column(series: pd.Series) -> pd.Series:
    """Min-max normalize a series to [0, 1]."""
    smin, smax = series.min(), series.max()
    if smax - smin < 1e-9:
        return pd.Series(0.5, index=series.index)
    return (series - smin) / (smax - smin)


def classify_zones(
    metrics_df: pd.DataFrame,
    validation_zones: Optional[dict[str, str]] = None,
) -> pd.DataFrame:
    """
    Score and classify each zone as transmission/generation/both/unconstrained.

    Args:
        metrics_df: Output of compute_zone_metrics().
        validation_zones: Optional dict of {zone: expected_constraint_type}
            for validation logging. Pass None to skip validation.

    Returns:
        The metrics DataFrame augmented with:
          transmission_score, generation_score, classification
    """
    df = metrics_df.copy()

    # Normalize each metric to [0, 1] across all zones
    df["norm_cong_ratio"] = _normalize_column(df["congestion_ratio"])
    df["norm_cong_vol"] = _normalize_column(df["congestion_volatility"])
    df["norm_cong_hours"] = _normalize_column(df["congested_hours_pct"])
    df["norm_peak_offpeak"] = _normalize_column(df["peak_offpeak_ratio"])

    df["norm_energy_dev"] = _normalize_column(df["energy_deviation"])
    df["norm_energy_vol"] = _normalize_column(df["energy_volatility"])
    df["norm_loss"] = _normalize_column(df["loss_ratio"])
    df["norm_high_energy"] = _normalize_column(df["high_energy_pct"])

    # Weighted scores
    df["transmission_score"] = (
        CONGESTION_RATIO_WEIGHT * df["norm_cong_ratio"]
        + CONGESTION_VOLATILITY_WEIGHT * df["norm_cong_vol"]
        + CONGESTION_HOURS_PCT_WEIGHT * df["norm_cong_hours"]
        + PEAK_OFFPEAK_RATIO_WEIGHT * df["norm_peak_offpeak"]
    )

    df["generation_score"] = (
        ENERGY_DEVIATION_WEIGHT * df["norm_energy_dev"]
        + ENERGY_VOLATILITY_WEIGHT * df["norm_energy_vol"]
        + LOSS_COMPONENT_WEIGHT * df["norm_loss"]
        + ENERGY_HOURS_PCT_WEIGHT * df["norm_high_energy"]
    )

    # Classify
    def _classify(row):
        t = row["transmission_score"] >= CLASSIFICATION_THRESHOLD
        g = row["generation_score"] >= CLASSIFICATION_THRESHOLD
        if t and g:
            return "both"
        elif t:
            return "transmission"
        elif g:
            return "generation"
        else:
            return "unconstrained"

    df["classification"] = df.apply(_classify, axis=1)

    # Log summary
    counts = df["classification"].value_counts()
    logger.info(f"Classification results: {counts.to_dict()}")

    # Optional validation against known constraint patterns
    if validation_zones:
        _validate(df, validation_zones)

    return df


def _validate(df: pd.DataFrame, known_constraints: dict[str, str]):
    """
    Check classification against known constraint patterns.

    Args:
        known_constraints: {zone_code: expected_type} where expected_type
            is "transmission", "generation", or "both".
    """
    classified = dict(zip(df["zone"], df["classification"]))

    for zone, expected in known_constraints.items():
        if zone in classified:
            cls = classified[zone]
            # Check if classification matches expectation
            if expected == "transmission" and cls in ("transmission", "both"):
                logger.info(f"Validation OK: {zone} classified as '{cls}' (expected transmission-related)")
            elif expected == "generation" and cls in ("generation", "both"):
                logger.info(f"Validation OK: {zone} classified as '{cls}' (expected generation-related)")
            elif cls == expected:
                logger.info(f"Validation OK: {zone} classified as '{cls}'")
            else:
                logger.warning(
                    f"Validation WARNING: {zone} classified as '{cls}', "
                    f"expected {expected}. T-score={df[df['zone']==zone]['transmission_score'].values[0]:.3f}"
                )


def get_constrained_hours(
    lmp_df: pd.DataFrame,
    zone: str,
    threshold: float = CONGESTION_THRESHOLD_DOLLARS,
    zone_column: str = "pnode_name",
    congestion_column: str = "congestion_price_da",
) -> int:
    """Count hours where |congestion| exceeds threshold for a zone."""
    zone_data = lmp_df[lmp_df[zone_column] == zone]
    return int((zone_data[congestion_column].abs() > threshold).sum())


def get_congestion_value(
    lmp_df: pd.DataFrame,
    zone: str,
    zone_column: str = "pnode_name",
    congestion_column: str = "congestion_price_da",
) -> float:
    """Average absolute congestion cost ($/MWh) for a zone."""
    zone_data = lmp_df[lmp_df[zone_column] == zone]
    return float(zone_data[congestion_column].abs().mean())
