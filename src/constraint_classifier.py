"""
Grid constraint classifier using LMP decomposition.

Classifies PJM zones by constraint type:
  - "transmission": congestion-dominated (flow limits on transmission lines)
  - "generation": energy-price-dominated (insufficient local generation)
  - "both": significant transmission AND generation constraints
  - "unconstrained": minimal constraints of either type

Uses congestion and energy price components from day-ahead hourly LMPs
to compute per-zone scoring metrics.
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

# Peak hours: HE 7-22 (EPT), matching PJM peak period
PEAK_HOURS = set(range(7, 23))


def compute_zone_metrics(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute per-zone constraint metrics from hourly LMP data.

    Input DataFrame must have columns:
      datetime_beginning_ept, pnode_name, zone, total_lmp_da,
      congestion_price_da, marginal_loss_price_da, system_energy_price_da, hour
    """
    # For zone-type LMPs, the zone name is in pnode_name (zone column is null).
    # Exclude RTO-level aggregates like PJM-RTO and MID-ATL/APS.
    rto_aggregates = {"PJM-RTO", "MID-ATL/APS"}
    zone_df = df[~df["pnode_name"].isin(rto_aggregates)].copy()
    zone_col = "pnode_name"

    # Mark peak/off-peak
    zone_df["is_peak"] = zone_df["hour"].isin(PEAK_HOURS)

    # System average energy price per hour
    sys_energy = zone_df.groupby("datetime_beginning_ept")["system_energy_price_da"].mean()

    metrics = []

    for zone_name, zdf in zone_df.groupby(zone_col):
        n_hours = len(zdf)
        if n_hours < 100:  # Skip zones with insufficient data
            continue

        cong = zdf["congestion_price_da"]
        lmp = zdf["total_lmp_da"]
        energy = zdf["system_energy_price_da"]
        loss = zdf["marginal_loss_price_da"]

        # ── Transmission metrics ──

        # 1. Congestion ratio: mean(|congestion|) / mean(|lmp|)
        congestion_ratio = cong.abs().mean() / max(lmp.abs().mean(), 0.01)

        # 2. Congestion volatility (CV = std/mean, normalized)
        cong_std = cong.std()
        cong_cv = cong_std / max(cong.abs().mean(), 0.01)

        # 3. Congested hours percentage
        congested_hours_pct = (cong.abs() > CONGESTION_THRESHOLD_DOLLARS).mean()

        # 4. Peak/off-peak congestion ratio
        peak_cong = zdf[zdf["is_peak"]]["congestion_price_da"].abs().mean()
        offpeak_cong = zdf[~zdf["is_peak"]]["congestion_price_da"].abs().mean()
        peak_offpeak_ratio = peak_cong / max(offpeak_cong, 0.01)

        # ── Generation metrics ──

        # 5. Energy price deviation from system average
        zone_hours = zdf.set_index("datetime_beginning_ept")
        merged = zone_hours.join(sys_energy, rsuffix="_sys")
        if "system_energy_price_da_sys" in merged.columns:
            energy_dev = (merged["system_energy_price_da"] - merged["system_energy_price_da_sys"]).abs().mean()
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


def classify_zones(metrics_df: pd.DataFrame) -> pd.DataFrame:
    """
    Score and classify each zone as transmission/generation/both/unconstrained.

    Returns the metrics DataFrame augmented with:
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

    # Validate against known constraints
    _validate(df)

    return df


def _validate(df: pd.DataFrame):
    """Check classification against known PJM constraint patterns."""
    known_transmission = {"DOM", "PEPCO", "BGE", "PSEG", "JCPL"}
    classified = dict(zip(df["zone"], df["classification"]))

    for zone in known_transmission:
        if zone in classified:
            cls = classified[zone]
            if cls in ("transmission", "both"):
                logger.info(f"Validation OK: {zone} classified as '{cls}' (expected transmission-related)")
            else:
                logger.warning(
                    f"Validation WARNING: {zone} classified as '{cls}', "
                    f"expected transmission or both. T-score={df[df['zone']==zone]['transmission_score'].values[0]:.3f}"
                )


def get_constrained_hours(
    lmp_df: pd.DataFrame,
    zone: str,
    threshold: float = CONGESTION_THRESHOLD_DOLLARS,
) -> int:
    """Count hours where |congestion| exceeds threshold for a zone."""
    zone_data = lmp_df[lmp_df["pnode_name"] == zone]
    return int((zone_data["congestion_price_da"].abs() > threshold).sum())


def get_congestion_value(
    lmp_df: pd.DataFrame,
    zone: str,
) -> float:
    """Average absolute congestion cost ($/MWh) for a zone."""
    zone_data = lmp_df[lmp_df["pnode_name"] == zone]
    return float(zone_data["congestion_price_da"].abs().mean())
