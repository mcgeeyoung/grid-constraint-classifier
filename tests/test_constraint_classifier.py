"""Tests for core.constraint_classifier."""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.constraint_classifier import (
    compute_zone_metrics,
    classify_zones,
    _normalize_column,
    get_constrained_hours,
    get_congestion_value,
    CLASSIFICATION_THRESHOLD,
    CONGESTION_THRESHOLD_DOLLARS,
    DEFAULT_COLUMNS,
)


# ── Helpers ──

def _make_lmp_df(zones: dict[str, dict], hours: int = 200) -> pd.DataFrame:
    """Build a synthetic LMP DataFrame for multiple zones.

    Args:
        zones: {zone_name: {"congestion": float, "energy": float, "loss": float, "lmp": float}}
        hours: Number of hourly records per zone.
    """
    rows = []
    timestamps = pd.date_range("2024-01-01", periods=hours, freq="h")
    for zone_name, vals in zones.items():
        for i, ts in enumerate(timestamps):
            rows.append({
                "datetime_beginning_ept": ts,
                "pnode_name": zone_name,
                "total_lmp_da": vals.get("lmp", 50.0),
                "congestion_price_da": vals.get("congestion", 0.0),
                "marginal_loss_price_da": vals.get("loss", 0.0),
                "system_energy_price_da": vals.get("energy", 50.0),
                "hour": ts.hour,
            })
    return pd.DataFrame(rows)


# ── _normalize_column tests ──

class TestNormalizeColumn:
    def test_basic_normalization(self):
        s = pd.Series([0, 5, 10])
        result = _normalize_column(s)
        assert result.iloc[0] == pytest.approx(0.0)
        assert result.iloc[1] == pytest.approx(0.5)
        assert result.iloc[2] == pytest.approx(1.0)

    def test_constant_series_returns_half(self):
        s = pd.Series([7.0, 7.0, 7.0])
        result = _normalize_column(s)
        assert all(v == pytest.approx(0.5) for v in result)

    def test_negative_values(self):
        s = pd.Series([-10, 0, 10])
        result = _normalize_column(s)
        assert result.iloc[0] == pytest.approx(0.0)
        assert result.iloc[1] == pytest.approx(0.5)
        assert result.iloc[2] == pytest.approx(1.0)

    def test_single_element(self):
        s = pd.Series([42.0])
        result = _normalize_column(s)
        assert result.iloc[0] == pytest.approx(0.5)

    def test_near_zero_range(self):
        """Range smaller than 1e-9 should return 0.5."""
        s = pd.Series([1.0, 1.0 + 1e-12])
        result = _normalize_column(s)
        assert all(v == pytest.approx(0.5) for v in result)


# ── compute_zone_metrics tests ──

class TestComputeZoneMetrics:
    def test_basic_metrics(self):
        df = _make_lmp_df({
            "ZONE_A": {"congestion": 5.0, "energy": 45.0, "loss": 1.0, "lmp": 51.0},
        })
        metrics = compute_zone_metrics(df)
        assert len(metrics) == 1
        assert metrics.iloc[0]["zone"] == "ZONE_A"
        assert metrics.iloc[0]["n_hours"] == 200

    def test_excludes_rto_aggregates(self):
        df = _make_lmp_df({
            "ZONE_A": {"congestion": 5.0, "energy": 45.0, "loss": 1.0, "lmp": 51.0},
            "PJM-RTO": {"congestion": 1.0, "energy": 48.0, "loss": 1.0, "lmp": 50.0},
        })
        metrics = compute_zone_metrics(df, rto_aggregates={"PJM-RTO"})
        assert len(metrics) == 1
        assert metrics.iloc[0]["zone"] == "ZONE_A"

    def test_skips_zones_under_100_hours(self):
        df = _make_lmp_df({"ZONE_A": {"congestion": 5.0}}, hours=50)
        metrics = compute_zone_metrics(df)
        assert len(metrics) == 0

    def test_congestion_ratio_positive(self):
        df = _make_lmp_df({
            "ZONE_A": {"congestion": 10.0, "energy": 40.0, "loss": 1.0, "lmp": 51.0},
        })
        metrics = compute_zone_metrics(df)
        assert metrics.iloc[0]["congestion_ratio"] > 0

    def test_multiple_zones(self):
        df = _make_lmp_df({
            "ZONE_A": {"congestion": 10.0, "energy": 40.0, "loss": 1.0, "lmp": 51.0},
            "ZONE_B": {"congestion": 0.1, "energy": 49.0, "loss": 0.5, "lmp": 49.6},
        })
        metrics = compute_zone_metrics(df)
        assert len(metrics) == 2

    def test_custom_peak_hours(self):
        """Custom peak hours should change peak/offpeak ratio calculation."""
        df = _make_lmp_df({
            "ZONE_A": {"congestion": 5.0, "energy": 45.0, "loss": 1.0, "lmp": 51.0},
        })
        # Using a narrow peak window
        metrics = compute_zone_metrics(df, peak_hours={12, 13, 14})
        assert len(metrics) == 1
        assert "peak_offpeak_ratio" in metrics.columns


# ── classify_zones tests ──

class TestClassifyZones:
    def _make_metrics_df(self, zone_data: list[dict]) -> pd.DataFrame:
        """Build a metrics DataFrame matching compute_zone_metrics output."""
        required = [
            "zone", "n_hours", "congestion_ratio", "congestion_volatility",
            "congested_hours_pct", "peak_offpeak_ratio", "energy_deviation",
            "energy_volatility", "loss_ratio", "high_energy_pct",
            "avg_congestion", "avg_abs_congestion", "avg_lmp",
            "max_congestion", "congestion_std",
        ]
        defaults = {k: 0.0 for k in required}
        defaults["zone"] = "UNKNOWN"
        defaults["n_hours"] = 200
        rows = [{**defaults, **d} for d in zone_data]
        return pd.DataFrame(rows)

    def test_uniform_zones_same_classification(self):
        """Zones with identical metrics should get the same classification.

        When all zones are identical, _normalize_column returns 0.5 for
        all values, so scores land exactly at 0.5 (the threshold). The
        classification depends on whether >= is used (it is), so uniform
        zones classify as 'both' since both scores equal the threshold.
        """
        df = self._make_metrics_df([{"zone": "Z1"}, {"zone": "Z2"}])
        result = classify_zones(df)
        # Both zones should get the same classification
        assert result.iloc[0]["classification"] == result.iloc[1]["classification"]

    def test_transmission_constrained(self):
        """Zone with high transmission metrics and low generation."""
        df = self._make_metrics_df([
            {"zone": "Z_HIGH_T", "congestion_ratio": 10.0,
             "congestion_volatility": 5.0, "congested_hours_pct": 0.8,
             "peak_offpeak_ratio": 3.0},
            {"zone": "Z_LOW", "congestion_ratio": 0.01,
             "congestion_volatility": 0.01, "congested_hours_pct": 0.01,
             "peak_offpeak_ratio": 1.0},
        ])
        result = classify_zones(df)
        high_t = result[result["zone"] == "Z_HIGH_T"].iloc[0]
        assert high_t["classification"] in ("transmission", "both")
        assert high_t["transmission_score"] >= CLASSIFICATION_THRESHOLD

    def test_generation_constrained(self):
        """Zone with high generation metrics and low transmission."""
        df = self._make_metrics_df([
            {"zone": "Z_HIGH_G", "energy_deviation": 10.0,
             "energy_volatility": 5.0, "loss_ratio": 0.3,
             "high_energy_pct": 0.7},
            {"zone": "Z_LOW", "energy_deviation": 0.01,
             "energy_volatility": 0.01, "loss_ratio": 0.001,
             "high_energy_pct": 0.01},
        ])
        result = classify_zones(df)
        high_g = result[result["zone"] == "Z_HIGH_G"].iloc[0]
        assert high_g["classification"] in ("generation", "both")
        assert high_g["generation_score"] >= CLASSIFICATION_THRESHOLD

    def test_both_constrained(self):
        """Zone with high metrics on both dimensions."""
        df = self._make_metrics_df([
            {"zone": "Z_BOTH", "congestion_ratio": 10.0,
             "congestion_volatility": 5.0, "congested_hours_pct": 0.8,
             "peak_offpeak_ratio": 3.0, "energy_deviation": 10.0,
             "energy_volatility": 5.0, "loss_ratio": 0.3,
             "high_energy_pct": 0.7},
            {"zone": "Z_LOW"},
        ])
        result = classify_zones(df)
        both = result[result["zone"] == "Z_BOTH"].iloc[0]
        assert both["classification"] == "both"

    def test_output_columns_present(self):
        df = self._make_metrics_df([{"zone": "Z1"}])
        result = classify_zones(df)
        assert "transmission_score" in result.columns
        assert "generation_score" in result.columns
        assert "classification" in result.columns


# ── Utility function tests ──

class TestUtilityFunctions:
    def test_get_constrained_hours(self):
        df = _make_lmp_df({"ZONE_A": {"congestion": 5.0}}, hours=200)
        hours = get_constrained_hours(df, "ZONE_A")
        assert hours == 200  # |5.0| > 2.0 threshold

    def test_get_constrained_hours_below_threshold(self):
        df = _make_lmp_df({"ZONE_A": {"congestion": 1.0}}, hours=200)
        hours = get_constrained_hours(df, "ZONE_A")
        assert hours == 0  # |1.0| < 2.0 threshold

    def test_get_congestion_value(self):
        df = _make_lmp_df({"ZONE_A": {"congestion": -5.0}}, hours=200)
        value = get_congestion_value(df, "ZONE_A")
        assert value == pytest.approx(5.0)
