"""Tests for core.congestion_calculator."""

import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.congestion_calculator import (
    compute_congestion_metrics,
    compute_duration_curve,
)


def _make_hourly_df(hours: int, demand: float, net_imports: float) -> pd.DataFrame:
    """Helper: uniform hourly data."""
    return pd.DataFrame({
        "timestamp_utc": pd.date_range("2024-01-01", periods=hours, freq="h"),
        "demand_mw": demand,
        "net_generation_mw": demand - net_imports,
        "total_interchange_mw": -net_imports,
        "net_imports_mw": net_imports,
    })


class TestZeroImportBA:
    """A BA that never imports should produce zero congestion metrics."""

    def test_zero_import_scores(self):
        df = _make_hourly_df(8760, demand=1000.0, net_imports=-200.0)
        result = compute_congestion_metrics(
            df, transfer_limit_mw=500.0,
            period_start=date(2024, 1, 1),
            period_end=date(2024, 12, 31),
        )
        assert result["hours_total"] == 8760
        assert result["hours_importing"] == 0
        assert result["pct_hours_importing"] == 0.0
        assert result["hours_above_80"] == 0
        assert result["hours_above_90"] == 0
        assert result["hours_above_95"] == 0
        assert result["avg_import_pct_of_load"] == 0.0
        assert result["data_quality_flag"] == "good"

    def test_zero_import_duration_curve(self):
        df = _make_hourly_df(8760, demand=1000.0, net_imports=-200.0)
        curve = compute_duration_curve(df, transfer_limit_mw=500.0)
        assert len(curve) == 8760
        assert all(v < 0 for v in curve)


class TestFullyImportingBA:
    """A BA that imports at 100% of transfer limit every hour."""

    def test_full_import_scores(self):
        df = _make_hourly_df(8760, demand=1000.0, net_imports=500.0)
        result = compute_congestion_metrics(
            df, transfer_limit_mw=500.0,
            period_start=date(2024, 1, 1),
            period_end=date(2024, 12, 31),
        )
        assert result["hours_total"] == 8760
        assert result["hours_importing"] == 8760
        assert result["pct_hours_importing"] == 1.0
        assert result["hours_above_80"] == 8760
        assert result["hours_above_90"] == 8760
        assert result["hours_above_95"] == 8760
        assert result["avg_import_pct_of_load"] == pytest.approx(0.5, abs=0.01)
        assert result["max_import_pct_of_load"] == pytest.approx(0.5, abs=0.01)

    def test_full_import_duration_curve(self):
        df = _make_hourly_df(8760, demand=1000.0, net_imports=500.0)
        curve = compute_duration_curve(df, transfer_limit_mw=500.0)
        assert len(curve) == 8760
        assert all(abs(v - 1.0) < 0.01 for v in curve)


class TestPartialImportBA:
    """A BA that imports at 90% utilization for half the year, 0 for rest."""

    def test_partial_scores(self):
        half = 4380
        importing = _make_hourly_df(half, demand=1000.0, net_imports=450.0)
        exporting = _make_hourly_df(half, demand=1000.0, net_imports=-100.0)
        # Fix timestamps for second half
        exporting["timestamp_utc"] = pd.date_range(
            "2024-07-01", periods=half, freq="h"
        )
        df = pd.concat([importing, exporting], ignore_index=True)

        result = compute_congestion_metrics(
            df, transfer_limit_mw=500.0,
            period_start=date(2024, 1, 1),
            period_end=date(2024, 12, 31),
        )
        assert result["hours_total"] == 8760
        assert result["hours_importing"] == half
        assert result["pct_hours_importing"] == pytest.approx(0.5, abs=0.01)
        # 450/500 = 0.90 exactly, so above 80% threshold but not strictly above 90%
        assert result["hours_above_80"] == half
        assert result["hours_above_90"] == 0  # 0.90 is not > 0.90
        assert result["hours_above_95"] == 0


class TestPartialYear:
    """Partial-year data should be flagged appropriately."""

    def test_sparse_data(self):
        df = _make_hourly_df(2000, demand=1000.0, net_imports=300.0)
        result = compute_congestion_metrics(
            df, transfer_limit_mw=500.0,
            period_start=date(2024, 1, 1),
            period_end=date(2024, 12, 31),
        )
        assert result["hours_total"] == 2000
        assert result["data_quality_flag"] == "sparse"

    def test_partial_data(self):
        df = _make_hourly_df(7000, demand=1000.0, net_imports=300.0)
        result = compute_congestion_metrics(
            df, transfer_limit_mw=500.0,
            period_start=date(2024, 1, 1),
            period_end=date(2024, 12, 31),
        )
        assert result["hours_total"] == 7000
        assert result["data_quality_flag"] == "partial"


class TestEdgeCases:
    """Edge cases: empty data, zero transfer limit, zero demand."""

    def test_empty_dataframe(self):
        df = pd.DataFrame(columns=[
            "timestamp_utc", "demand_mw", "net_generation_mw",
            "total_interchange_mw", "net_imports_mw",
        ])
        result = compute_congestion_metrics(
            df, transfer_limit_mw=500.0,
            period_start=date(2024, 1, 1),
            period_end=date(2024, 12, 31),
        )
        assert result["hours_total"] == 0
        assert result["data_quality_flag"] == "sparse"

    def test_zero_transfer_limit(self):
        df = _make_hourly_df(100, demand=1000.0, net_imports=300.0)
        result = compute_congestion_metrics(
            df, transfer_limit_mw=0.0,
            period_start=date(2024, 1, 1),
            period_end=date(2024, 12, 31),
        )
        assert result["hours_total"] == 0
        assert result["data_quality_flag"] == "no_transfer_limit"

    def test_none_transfer_limit(self):
        df = _make_hourly_df(100, demand=1000.0, net_imports=300.0)
        result = compute_congestion_metrics(
            df, transfer_limit_mw=None,
            period_start=date(2024, 1, 1),
            period_end=date(2024, 12, 31),
        )
        assert result["data_quality_flag"] == "no_transfer_limit"

    def test_utilization_above_one_allowed(self):
        """Values above 1.0 should NOT be clipped."""
        df = _make_hourly_df(100, demand=1000.0, net_imports=600.0)
        result = compute_congestion_metrics(
            df, transfer_limit_mw=500.0,
            period_start=date(2024, 1, 1),
            period_end=date(2024, 12, 31),
        )
        # 600/500 = 1.2, should count as above all thresholds
        assert result["hours_above_80"] == 100
        assert result["hours_above_90"] == 100
        assert result["hours_above_95"] == 100

    def test_duration_curve_empty(self):
        df = pd.DataFrame(columns=[
            "timestamp_utc", "demand_mw", "net_generation_mw",
            "total_interchange_mw", "net_imports_mw",
        ])
        curve = compute_duration_curve(df, transfer_limit_mw=500.0)
        assert curve == []

    def test_duration_curve_sorted_descending(self):
        """Duration curve should be sorted highest to lowest."""
        hours = 100
        imports = np.random.uniform(-200, 600, hours)
        df = pd.DataFrame({
            "timestamp_utc": pd.date_range("2024-01-01", periods=hours, freq="h"),
            "demand_mw": 1000.0,
            "net_generation_mw": 1000.0 - imports,
            "total_interchange_mw": -imports,
            "net_imports_mw": imports,
        })
        curve = compute_duration_curve(df, transfer_limit_mw=500.0)
        assert len(curve) == hours
        assert curve == sorted(curve, reverse=True)


class TestEconomicMetrics:
    """Tests for LMP-based economic scoring."""

    def test_with_interface_lmp(self):
        hours = 100
        df = _make_hourly_df(hours, demand=1000.0, net_imports=450.0)
        ts = df["timestamp_utc"]

        lmp_df = pd.DataFrame({
            "timestamp_utc": ts,
            "lmp": 50.0,  # $50/MWh at interface
        })
        baseline_df = pd.DataFrame({
            "timestamp_utc": ts,
            "lmp": 40.0,  # $40/MWh baseline
        })

        result = compute_congestion_metrics(
            df, transfer_limit_mw=500.0,
            period_start=date(2024, 1, 1),
            period_end=date(2024, 12, 31),
            interface_lmp_df=lmp_df,
            baseline_lmp_df=baseline_df,
        )
        assert result["lmp_coverage"] == "full"
        assert result["hours_with_lmp_data"] == hours
        assert result["avg_congestion_premium"] == pytest.approx(10.0, abs=0.1)
        # COS = 100 hours * $10 premium / 1000 = $1.0/kW
        assert result["congestion_opportunity_score"] == pytest.approx(1.0, abs=0.1)

    def test_no_lmp_returns_none(self):
        df = _make_hourly_df(100, demand=1000.0, net_imports=450.0)
        result = compute_congestion_metrics(
            df, transfer_limit_mw=500.0,
            period_start=date(2024, 1, 1),
            period_end=date(2024, 12, 31),
        )
        assert result["lmp_coverage"] == "none"
        assert result["congestion_opportunity_score"] is None
