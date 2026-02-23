"""
Node-level congestion hotspot analysis.

Within a zone, all nodes share the same system energy price, so the
energy-based score components are identical. Congestion and marginal loss
are the differentiators. This module ranks nodes by congestion severity
within each constrained zone.

Scoring metrics (per node, from hourly congestion data):
  1. Congestion magnitude   (30%) - avg(|congestion|)
  2. Congestion volatility  (20%) - std / max(avg(|congestion|), 0.01)
  3. Congested hours %      (25%) - % hours with |congestion| > $2/MWh
  4. Peak/off-peak ratio    (15%) - peak |congestion| / off-peak |congestion|
  5. Extreme events         (10%) - hours with |congestion| > zone 95th pct

Scores are min-max normalized within each zone and combined into a
weighted "congestion severity score" (0-1).

ISO-agnostic: accepts peak_hours and cache_dir as parameters.
"""

import json
import logging
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# Metric weights
MAGNITUDE_WEIGHT = 0.30
VOLATILITY_WEIGHT = 0.20
CONGESTED_HOURS_WEIGHT = 0.25
PEAK_OFFPEAK_WEIGHT = 0.15
EXTREME_EVENTS_WEIGHT = 0.10

# Thresholds
CONGESTION_THRESHOLD = 2.0  # $/MWh

# Default peak hours (matches PJM HE 7-22 EPT)
DEFAULT_PEAK_HOURS = set(range(7, 23))

# Tier boundaries
TIER_CRITICAL = 0.75
TIER_ELEVATED = 0.50
TIER_MODERATE = 0.25


def _assign_tier(score: float) -> str:
    if score >= TIER_CRITICAL:
        return "critical"
    elif score >= TIER_ELEVATED:
        return "elevated"
    elif score >= TIER_MODERATE:
        return "moderate"
    else:
        return "low"


def compute_pnode_metrics(
    node_lmp_df: pd.DataFrame,
    zone: str,
    peak_hours: Optional[set[int]] = None,
    congestion_column: str = "congestion_price_da",
    timestamp_column: str = "datetime_beginning_ept",
    node_id_column: str = "pnode_id",
    node_name_column: str = "pnode_name",
) -> pd.DataFrame:
    """
    Compute raw congestion metrics per node from hourly node-level LMPs.

    Args:
        node_lmp_df: DataFrame with columns including node_id, node_name,
                     congestion data, and timestamps.
        zone: Zone name (for logging).
        peak_hours: Set of hours considered peak. Default: 7-22.
        congestion_column: Column name for congestion price.
        timestamp_column: Column name for timestamp.
        node_id_column: Column name for node ID.
        node_name_column: Column name for node name.

    Returns:
        DataFrame with one row per node and raw metric columns.
    """
    if peak_hours is None:
        peak_hours = DEFAULT_PEAK_HOURS

    df = node_lmp_df.copy()

    # Ensure needed columns
    if congestion_column not in df.columns:
        logger.warning(f"{zone}: missing {congestion_column} column")
        return pd.DataFrame()

    # Derive hour if not present
    if "hour" not in df.columns:
        df["hour"] = pd.to_datetime(df[timestamp_column]).dt.hour

    df["is_peak"] = df["hour"].isin(peak_hours)
    df["abs_congestion"] = df[congestion_column].abs()

    # Deduplicate by node_name + timestamp: multiple node_ids at the same
    # bus (e.g. generating units) share identical congestion prices. Keep
    # one representative row per (name, hour) to avoid inflated counts and
    # duplicate hotspot entries.
    has_name = node_name_column in df.columns
    has_id = node_id_column in df.columns

    if has_name and has_id:
        n_before = len(df)
        # Map each name to its first node_id for later reference
        name_to_id = df.groupby(node_name_column)[node_id_column].first()
        df = df.drop_duplicates(subset=[node_name_column, timestamp_column])
        n_after = len(df)
        if n_after < n_before:
            logger.info(
                f"{zone}: deduplicated {n_before:,} -> {n_after:,} rows "
                f"(collapsed unit-level node_ids to bus names)"
            )

    # Zone-wide 95th percentile for extreme event threshold
    zone_p95 = df["abs_congestion"].quantile(0.95)

    # Group by node_name (physical bus), not node_id (per-unit)
    pnode_col = node_name_column if has_name else node_id_column

    metrics = []
    for pnode_key, pdf in df.groupby(pnode_col):
        n_hours = len(pdf)
        if n_hours < 24:  # Skip nodes with < 1 day of data
            continue

        cong = pdf[congestion_column]
        abs_cong = pdf["abs_congestion"]

        # 1. Congestion magnitude
        avg_abs_cong = abs_cong.mean()

        # 2. Congestion volatility (CV)
        cong_vol = cong.std() / max(avg_abs_cong, 0.01)

        # 3. Congested hours %
        congested_pct = (abs_cong > CONGESTION_THRESHOLD).mean()

        # 4. Peak/off-peak ratio
        peak_cong = pdf[pdf["is_peak"]]["abs_congestion"].mean() if pdf["is_peak"].any() else 0
        offpeak_cong = pdf[~pdf["is_peak"]]["abs_congestion"].mean() if (~pdf["is_peak"]).any() else 0
        peak_offpeak = peak_cong / max(offpeak_cong, 0.01)

        # 5. Extreme events
        extreme_hours = int((abs_cong > zone_p95).sum())

        # Representative node_id for this name
        if pnode_col == node_name_column and has_name and has_id:
            pnode_id = int(name_to_id.get(pnode_key, 0))
            pnode_name = pnode_key
        elif has_id:
            pnode_id = pnode_key
            pnode_name = pdf[node_name_column].iloc[0] if has_name else str(pnode_key)
        else:
            pnode_id = 0
            pnode_name = str(pnode_key)

        metrics.append({
            "pnode_id": pnode_id,
            "pnode_name": pnode_name,
            "n_hours": n_hours,
            "avg_congestion": round(avg_abs_cong, 4),
            "max_congestion": round(abs_cong.max(), 2),
            "congestion_volatility": round(min(cong_vol, 20), 4),
            "congested_hours_pct": round(congested_pct, 4),
            "peak_offpeak_ratio": round(min(peak_offpeak, 20), 4),
            "extreme_event_hours": extreme_hours,
        })

    result = pd.DataFrame(metrics)
    logger.info(f"{zone}: computed metrics for {len(result)} nodes")
    return result


def _min_max_normalize(series: pd.Series) -> pd.Series:
    """Min-max normalize to [0, 1] within a zone's nodes."""
    smin, smax = series.min(), series.max()
    if smax - smin < 1e-9:
        return pd.Series(0.5, index=series.index)
    return (series - smin) / (smax - smin)


def score_pnodes(metrics_df: pd.DataFrame) -> pd.DataFrame:
    """
    Normalize metrics within zone and compute weighted severity score.

    Args:
        metrics_df: Output of compute_pnode_metrics()

    Returns:
        DataFrame with severity_score and tier columns added.
    """
    if metrics_df.empty:
        return metrics_df

    df = metrics_df.copy()

    # Min-max normalize each metric within this zone's nodes
    df["norm_magnitude"] = _min_max_normalize(df["avg_congestion"])
    df["norm_volatility"] = _min_max_normalize(df["congestion_volatility"])
    df["norm_congested_hrs"] = _min_max_normalize(df["congested_hours_pct"])
    df["norm_peak_offpeak"] = _min_max_normalize(df["peak_offpeak_ratio"])
    df["norm_extreme"] = _min_max_normalize(df["extreme_event_hours"])

    # Weighted composite score
    df["severity_score"] = (
        MAGNITUDE_WEIGHT * df["norm_magnitude"]
        + VOLATILITY_WEIGHT * df["norm_volatility"]
        + CONGESTED_HOURS_WEIGHT * df["norm_congested_hrs"]
        + PEAK_OFFPEAK_WEIGHT * df["norm_peak_offpeak"]
        + EXTREME_EVENTS_WEIGHT * df["norm_extreme"]
    )

    df["severity_score"] = df["severity_score"].round(4)
    df["tier"] = df["severity_score"].apply(_assign_tier)

    # Drop intermediate normalized columns
    df = df.drop(columns=[
        "norm_magnitude", "norm_volatility", "norm_congested_hrs",
        "norm_peak_offpeak", "norm_extreme",
    ])

    return df.sort_values("severity_score", ascending=False).reset_index(drop=True)


def compute_constraint_loadshapes(
    node_lmp_df: pd.DataFrame,
    zone: str,
    congestion_column: str = "congestion_price_da",
    timestamp_column: str = "datetime_beginning_ept",
    node_name_column: str = "pnode_name",
    node_id_column: str = "pnode_id",
) -> dict:
    """
    Compute monthly x hourly (12x24) constraint load shapes per node.

    For each node, produces 288 coefficients (12 months x 24 hours) showing
    the relative intensity of congestion at each (month, hour) slot,
    normalized to [0, 1] by the node's own peak value.

    Returns:
        {node_name: {"loadshape": {"1": [24 floats], ...}, "max_mwh": float}}
    """
    df = node_lmp_df.copy()

    if congestion_column not in df.columns:
        logger.warning(f"{zone}: missing {congestion_column} for loadshapes")
        return {}

    ts = pd.to_datetime(df[timestamp_column])
    if "month" not in df.columns:
        df["month"] = ts.dt.month
    if "hour" not in df.columns:
        df["hour"] = ts.dt.hour

    df["abs_congestion"] = df[congestion_column].abs()

    # Deduplicate unit-level node_ids to bus names (same logic as metrics)
    has_name = node_name_column in df.columns
    has_id = node_id_column in df.columns
    if has_name and has_id:
        df = df.drop_duplicates(subset=[node_name_column, timestamp_column])

    # Group by node_name (physical bus) to match metrics dedup
    pnode_col = node_name_column if has_name else node_id_column

    # Single vectorized groupby: mean abs congestion per (node, month, hour)
    grouped = (
        df.groupby([pnode_col, "month", "hour"])["abs_congestion"]
        .mean()
    )

    result = {}
    for pnode_key, pnode_group in grouped.groupby(level=0):
        # Unstack into month x hour (drop node level from index)
        series = pnode_group.droplevel(0)
        matrix = series.unstack(level="hour")  # rows=month, cols=hour

        peak_val = matrix.max().max()
        if peak_val < 1e-6:
            continue  # skip effectively uncongested nodes

        # Normalize to [0, 1] by node's own max
        normed = matrix / peak_val

        # Build dict: {"1": [24 floats], ..., "12": [24 floats]}
        loadshape = {}
        for month_num in range(1, 13):
            if month_num in normed.index:
                row = normed.loc[month_num]
                loadshape[str(month_num)] = [
                    round(row.get(h, 0.0), 4) for h in range(24)
                ]
            else:
                loadshape[str(month_num)] = [0.0] * 24

        result[pnode_key] = {
            "loadshape": loadshape,
            "max_mwh": round(float(peak_val), 4),
        }

    logger.info(f"{zone}: computed constraint loadshapes for {len(result)} nodes")
    return result


def analyze_zone_pnodes(
    node_lmp_df: pd.DataFrame,
    zone: str,
    peak_hours: Optional[set[int]] = None,
    congestion_column: str = "congestion_price_da",
    timestamp_column: str = "datetime_beginning_ept",
    node_id_column: str = "pnode_id",
    node_name_column: str = "pnode_name",
) -> dict:
    """
    Full node congestion analysis for a single zone.

    Returns dict with zone summary, tier distribution, and top hotspots.
    """
    metrics_df = compute_pnode_metrics(
        node_lmp_df, zone,
        peak_hours=peak_hours,
        congestion_column=congestion_column,
        timestamp_column=timestamp_column,
        node_id_column=node_id_column,
        node_name_column=node_name_column,
    )
    if metrics_df.empty:
        return {
            "zone": zone,
            "total_pnodes": 0,
            "tier_distribution": {"critical": 0, "elevated": 0, "moderate": 0, "low": 0},
            "hotspots": [],
        }

    scored_df = score_pnodes(metrics_df)

    # Tier distribution
    tier_counts = scored_df["tier"].value_counts().to_dict()
    tier_dist = {
        "critical": tier_counts.get("critical", 0),
        "elevated": tier_counts.get("elevated", 0),
        "moderate": tier_counts.get("moderate", 0),
        "low": tier_counts.get("low", 0),
    }

    # Top 10 hotspots
    top = scored_df.head(10)
    hotspots = []
    for _, row in top.iterrows():
        hotspots.append({
            "pnode_name": row["pnode_name"],
            "pnode_id": int(row["pnode_id"]) if not pd.isna(row["pnode_id"]) else None,
            "severity_score": row["severity_score"],
            "tier": row["tier"],
            "avg_congestion": row["avg_congestion"],
            "max_congestion": row["max_congestion"],
            "congested_hours_pct": row["congested_hours_pct"],
            "peak_offpeak_ratio": row["peak_offpeak_ratio"],
            "extreme_event_hours": row["extreme_event_hours"],
        })

    # All scored nodes (minimal fields for map display)
    all_scored = []
    for _, row in scored_df.iterrows():
        all_scored.append({
            "pnode_name": row["pnode_name"],
            "pnode_id": int(row["pnode_id"]) if not pd.isna(row.get("pnode_id")) else None,
            "severity_score": row["severity_score"],
            "tier": row["tier"],
            "avg_congestion": row["avg_congestion"],
            "max_congestion": row["max_congestion"],
        })

    # Constraint load shapes (monthly x hourly coefficients)
    loadshapes = compute_constraint_loadshapes(
        node_lmp_df, zone,
        congestion_column=congestion_column,
        timestamp_column=timestamp_column,
        node_name_column=node_name_column,
        node_id_column=node_id_column,
    )

    # Attach inline on hotspots for dashboard rendering (keyed by node_name)
    for hs in hotspots:
        name = hs["pnode_name"]
        if name in loadshapes:
            hs["constraint_loadshape"] = loadshapes[name]["loadshape"]
            hs["constraint_loadshape_max_mwh"] = loadshapes[name]["max_mwh"]

    total = len(scored_df)
    logger.info(
        f"{zone}: {total} nodes scored | "
        f"Critical={tier_dist['critical']} Elevated={tier_dist['elevated']} "
        f"Moderate={tier_dist['moderate']} Low={tier_dist['low']}"
    )

    return {
        "zone": zone,
        "total_pnodes": total,
        "tier_distribution": tier_dist,
        "hotspots": hotspots,
        "all_scored": all_scored,
        "constraint_loadshapes": loadshapes,
    }


def analyze_all_constrained_zones(
    zone_data_dict: dict,
    peak_hours: Optional[set[int]] = None,
    cache_path: Optional[Path] = None,
    congestion_column: str = "congestion_price_da",
    timestamp_column: str = "datetime_beginning_ept",
    node_id_column: str = "pnode_id",
    node_name_column: str = "pnode_name",
) -> dict:
    """
    Run node analysis across all constrained zones.

    Args:
        zone_data_dict: {zone: DataFrame} with node-level LMP data.
        peak_hours: Set of peak hours. Default: 7-22.
        cache_path: Path to save results JSON. None to skip caching.
        congestion_column: Column name for congestion price.
        timestamp_column: Column name for timestamp.
        node_id_column: Column name for node ID.
        node_name_column: Column name for node name.

    Returns:
        {zone: analysis_dict} for inclusion in the pipeline summary.
    """
    results = {}
    for zone, node_lmp_df in zone_data_dict.items():
        logger.info(f"Analyzing nodes for {zone}...")
        results[zone] = analyze_zone_pnodes(
            node_lmp_df, zone,
            peak_hours=peak_hours,
            congestion_column=congestion_column,
            timestamp_column=timestamp_column,
            node_id_column=node_id_column,
            node_name_column=node_name_column,
        )

    total_pnodes = sum(r["total_pnodes"] for r in results.values())
    total_critical = sum(r["tier_distribution"]["critical"] for r in results.values())
    logger.info(
        f"Node drill-down complete: {len(results)} zones, "
        f"{total_pnodes} total nodes, {total_critical} critical hotspots"
    )

    # Cache results if path specified
    if cache_path:
        _save_pnode_results(results, cache_path)

    return results


def _save_pnode_results(results: dict, cache_path: Path):
    """Cache node drilldown results to JSON for reuse without re-analysis."""
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    clean = {}
    for zone, analysis in results.items():
        clean[zone] = _make_serializable(analysis)
    with open(cache_path, "w") as f:
        json.dump(clean, f, indent=2)
    logger.info(f"Cached node drilldown results to {cache_path}")


def _make_serializable(obj):
    """Recursively convert numpy types to native Python for JSON."""
    if isinstance(obj, dict):
        return {k: _make_serializable(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_make_serializable(v) for v in obj]
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    return obj


def load_pnode_results(cache_path: Path) -> dict:
    """
    Load cached node drilldown results.

    Args:
        cache_path: Path to the cached results JSON file.

    Returns:
        {zone: analysis_dict} or {} if no cache exists.
    """
    if cache_path.exists():
        with open(cache_path) as f:
            results = json.load(f)
        total = sum(r.get("total_pnodes", 0) for r in results.values())
        logger.info(f"Loaded cached node drilldown: {len(results)} zones, {total} nodes")
        return results
    return {}
