"""
Import Congestion Calculator.

Pure-computation module that takes hourly BA data and produces congestion
metrics for a given period. No database or API dependencies.

Input: DataFrame with columns [timestamp_utc, demand_mw, net_generation_mw,
       total_interchange_mw, net_imports_mw] + a transfer_limit_mw value.
Output: dict of metrics that maps to a CongestionScore record.
"""

import logging
from datetime import date
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# Configurable thresholds for congestion hour counting
UTILIZATION_THRESHOLDS = [0.80, 0.90, 0.95]


def compute_congestion_metrics(
    hourly_df: pd.DataFrame,
    transfer_limit_mw: float,
    period_start: date,
    period_end: date,
    period_type: str = "year",
    interface_lmp_df: Optional[pd.DataFrame] = None,
    baseline_lmp_df: Optional[pd.DataFrame] = None,
) -> dict:
    """Compute congestion metrics for one BA over one period.

    Args:
        hourly_df: DataFrame with columns [timestamp_utc, demand_mw,
            net_generation_mw, total_interchange_mw, net_imports_mw].
            One row per hour for the period.
        transfer_limit_mw: Estimated transfer limit in MW (e.g., P99 of
            historical net imports). Must be > 0.
        period_start: First day of the period.
        period_end: Last day of the period.
        period_type: "month" or "year".
        interface_lmp_df: Optional DataFrame with columns [timestamp_utc, lmp]
            for the primary interface node. Used for economic metrics.
        baseline_lmp_df: Optional DataFrame with columns [timestamp_utc, lmp]
            for the regional baseline (e.g., NP15 hub). Used with
            interface_lmp_df to compute congestion premium.

    Returns:
        Dict of metrics matching CongestionScore columns.
    """
    if hourly_df.empty:
        return _empty_result(period_start, period_end, period_type)

    if transfer_limit_mw is None or transfer_limit_mw <= 0:
        return _empty_result(
            period_start, period_end, period_type,
            data_quality_flag="no_transfer_limit",
        )

    df = hourly_df.copy()

    # Compute import utilization (no clipping; values > 1.0 represent stress)
    df["import_utilization"] = df["net_imports_mw"] / transfer_limit_mw

    # Hours analysis
    hours_total = len(df)
    hours_importing = int((df["net_imports_mw"] > 0).sum())
    pct_hours_importing = hours_importing / hours_total if hours_total > 0 else 0.0

    # Hours above utilization thresholds
    hours_above_80 = int((df["import_utilization"] > 0.80).sum())
    hours_above_90 = int((df["import_utilization"] > 0.90).sum())
    hours_above_95 = int((df["import_utilization"] > 0.95).sum())

    # Import intensity (only for hours when BA is importing)
    importing_mask = df["net_imports_mw"] > 0
    if importing_mask.any() and df["demand_mw"].notna().any():
        import_pct = df.loc[importing_mask, "net_imports_mw"] / df.loc[importing_mask, "demand_mw"].replace(0, np.nan)
        avg_import_pct_of_load = float(import_pct.mean()) if import_pct.notna().any() else None
        max_import_pct_of_load = float(import_pct.max()) if import_pct.notna().any() else None
    else:
        avg_import_pct_of_load = 0.0
        max_import_pct_of_load = 0.0

    # Data quality assessment
    if hours_total >= 8000:
        data_quality_flag = "good"
    elif hours_total >= 6000:
        data_quality_flag = "partial"
    else:
        data_quality_flag = "sparse"

    result = {
        "period_start": period_start,
        "period_end": period_end,
        "period_type": period_type,
        "hours_total": hours_total,
        "hours_importing": hours_importing,
        "pct_hours_importing": round(pct_hours_importing, 4),
        "hours_above_80": hours_above_80,
        "hours_above_90": hours_above_90,
        "hours_above_95": hours_above_95,
        "avg_import_pct_of_load": round(avg_import_pct_of_load, 4) if avg_import_pct_of_load is not None else None,
        "max_import_pct_of_load": round(max_import_pct_of_load, 4) if max_import_pct_of_load is not None else None,
        "transfer_limit_used": transfer_limit_mw,
        "data_quality_flag": data_quality_flag,
        "lmp_coverage": "none",
        "hours_with_lmp_data": 0,
        "avg_congestion_premium": None,
        "congestion_opportunity_score": None,
    }

    # Economic metrics (if LMP data provided)
    if interface_lmp_df is not None and not interface_lmp_df.empty:
        econ = _compute_economic_metrics(
            df, interface_lmp_df, baseline_lmp_df, transfer_limit_mw
        )
        result.update(econ)

    return result


def compute_duration_curve(
    hourly_df: pd.DataFrame,
    transfer_limit_mw: float,
) -> list[float]:
    """Compute import utilization duration curve (sorted descending).

    Returns a list of import_utilization values sorted from highest to
    lowest, suitable for charting. Length equals number of hours in the data.
    """
    if hourly_df.empty or transfer_limit_mw is None or transfer_limit_mw <= 0:
        return []

    utilization = hourly_df["net_imports_mw"] / transfer_limit_mw
    return sorted(utilization.dropna().tolist(), reverse=True)


def _compute_economic_metrics(
    df: pd.DataFrame,
    interface_lmp_df: pd.DataFrame,
    baseline_lmp_df: Optional[pd.DataFrame],
    transfer_limit_mw: float,
) -> dict:
    """Compute economic congestion metrics using interface LMP data.

    Returns dict with lmp_coverage, hours_with_lmp_data,
    avg_congestion_premium, congestion_opportunity_score.
    """
    # Merge interface LMP onto hourly data by timestamp
    merged = df.merge(
        interface_lmp_df[["timestamp_utc", "lmp"]].rename(columns={"lmp": "interface_lmp"}),
        on="timestamp_utc",
        how="left",
    )

    hours_with_lmp = int(merged["interface_lmp"].notna().sum())
    total_hours = len(merged)

    if hours_with_lmp == 0:
        return {
            "lmp_coverage": "none",
            "hours_with_lmp_data": 0,
            "avg_congestion_premium": None,
            "congestion_opportunity_score": None,
        }

    # Determine LMP coverage level
    coverage_ratio = hours_with_lmp / total_hours
    if coverage_ratio >= 0.90:
        lmp_coverage = "full"
    elif coverage_ratio >= 0.50:
        lmp_coverage = "partial"
    else:
        lmp_coverage = "sparse"

    # Merge baseline LMP if available
    if baseline_lmp_df is not None and not baseline_lmp_df.empty:
        merged = merged.merge(
            baseline_lmp_df[["timestamp_utc", "lmp"]].rename(columns={"lmp": "baseline_lmp"}),
            on="timestamp_utc",
            how="left",
        )
    else:
        # Use median of interface LMP as a rough baseline
        merged["baseline_lmp"] = merged["interface_lmp"].median()

    # Congestion premium = interface_lmp - baseline_lmp
    merged["premium"] = merged["interface_lmp"] - merged["baseline_lmp"]

    # Average congestion premium across all hours with LMP data
    lmp_mask = merged["interface_lmp"].notna() & merged["baseline_lmp"].notna()
    avg_premium = float(merged.loc[lmp_mask, "premium"].mean()) if lmp_mask.any() else None

    # Congestion Opportunity Score:
    # Sum of premium for hours where import_utilization > 0.80, in $/kW
    stress_mask = (merged["import_utilization"] > 0.80) & lmp_mask
    if stress_mask.any():
        cos_raw = float(merged.loc[stress_mask, "premium"].clip(lower=0).sum())
        cos = cos_raw / 1000.0  # $/MWh*hours -> $/kW
    else:
        cos = 0.0

    return {
        "lmp_coverage": lmp_coverage,
        "hours_with_lmp_data": hours_with_lmp,
        "avg_congestion_premium": round(avg_premium, 2) if avg_premium is not None else None,
        "congestion_opportunity_score": round(cos, 2),
    }


def _empty_result(
    period_start: date,
    period_end: date,
    period_type: str,
    data_quality_flag: str = "sparse",
) -> dict:
    """Return a metrics dict with all values zeroed/null."""
    return {
        "period_start": period_start,
        "period_end": period_end,
        "period_type": period_type,
        "hours_total": 0,
        "hours_importing": 0,
        "pct_hours_importing": 0.0,
        "hours_above_80": 0,
        "hours_above_90": 0,
        "hours_above_95": 0,
        "avg_import_pct_of_load": None,
        "max_import_pct_of_load": None,
        "transfer_limit_used": None,
        "data_quality_flag": data_quality_flag,
        "lmp_coverage": "none",
        "hours_with_lmp_data": 0,
        "avg_congestion_premium": None,
        "congestion_opportunity_score": None,
    }
