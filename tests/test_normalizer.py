"""Tests for adapters.hosting_capacity.normalizer."""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from adapters.hosting_capacity.normalizer import (
    normalize_hosting_capacity,
    CONSTRAINT_MAP,
    CANONICAL_COLUMNS,
    MW_COLUMNS,
)
from adapters.hosting_capacity.base import UtilityHCConfig


def _make_config(**overrides) -> UtilityHCConfig:
    """Create a test UtilityHCConfig with sensible defaults."""
    defaults = dict(
        utility_code="test_util",
        utility_name="Test Utility",
        iso_id="pjm",
        states=["PA"],
        data_source_type="arcgis_feature",
        field_map={},
        capacity_unit="mw",
    )
    defaults.update(overrides)
    return UtilityHCConfig(**defaults)


def _make_raw_df(**col_overrides) -> pd.DataFrame:
    """Create a minimal raw DataFrame with required columns."""
    defaults = {
        "feeder_id_external": ["F001", "F002", "F003"],
        "feeder_name": ["Feeder A", "Feeder B", "Feeder C"],
        "hosting_capacity_mw": [5.0, 10.0, 3.0],
        "installed_dg_mw": [1.0, 2.0, 0.5],
        "queued_dg_mw": [0.5, 1.0, 0.0],
    }
    defaults.update(col_overrides)
    return pd.DataFrame(defaults)


# ── Field renaming ──

class TestFieldRenaming:
    def test_applies_field_map(self):
        config = _make_config(
            field_map={"HC_KW": "hosting_capacity_mw", "FEEDER_ID": "feeder_id_external"},
            capacity_unit="mw",
        )
        df = pd.DataFrame({
            "FEEDER_ID": ["F001"],
            "HC_KW": [10.0],
        })
        result = normalize_hosting_capacity(df, config)
        assert "hosting_capacity_mw" in result.columns
        assert "feeder_id_external" in result.columns

    def test_unmapped_columns_preserved(self):
        config = _make_config(field_map={"FEEDER_ID": "feeder_id_external"})
        df = pd.DataFrame({
            "FEEDER_ID": ["F001"],
            "extra_col": ["value"],
        })
        result = normalize_hosting_capacity(df, config)
        assert "extra_col" in result.columns


# ── kW to MW conversion ──

class TestUnitConversion:
    def test_kw_to_mw_conversion(self):
        config = _make_config(capacity_unit="kw")
        df = _make_raw_df(
            hosting_capacity_mw=[5000.0, 10000.0, 3000.0],
            installed_dg_mw=[1000.0, 2000.0, 500.0],
            queued_dg_mw=[500.0, 1000.0, 0.0],
        )
        result = normalize_hosting_capacity(df, config)
        assert result["hosting_capacity_mw"].iloc[0] == pytest.approx(5.0)
        assert result["installed_dg_mw"].iloc[0] == pytest.approx(1.0)
        assert result["queued_dg_mw"].iloc[0] == pytest.approx(0.5)

    def test_mw_not_converted(self):
        config = _make_config(capacity_unit="mw")
        df = _make_raw_df(hosting_capacity_mw=[5.0, 10.0, 3.0])
        result = normalize_hosting_capacity(df, config)
        assert result["hosting_capacity_mw"].iloc[0] == pytest.approx(5.0)

    def test_kw_conversion_handles_non_numeric(self):
        config = _make_config(capacity_unit="kw")
        df = _make_raw_df(hosting_capacity_mw=["5000", "bad", "3000"])
        result = normalize_hosting_capacity(df, config)
        assert result["hosting_capacity_mw"].iloc[0] == pytest.approx(5.0)
        assert pd.isna(result["hosting_capacity_mw"].iloc[1])
        assert result["hosting_capacity_mw"].iloc[2] == pytest.approx(3.0)


# ── Constraint canonicalization ──

class TestConstraintNormalization:
    def test_thermal_variants(self):
        config = _make_config()
        df = _make_raw_df(
            constraining_metric=["Thermal Limit", "OVERLOAD", " thermal "],
        )
        result = normalize_hosting_capacity(df, config)
        assert list(result["constraining_metric"]) == ["thermal", "thermal", "thermal"]

    def test_voltage_variants(self):
        config = _make_config()
        df = _make_raw_df(
            constraining_metric=["Voltage Rise", "OVERVOLTAGE", "steady state voltage"],
        )
        result = normalize_hosting_capacity(df, config)
        assert list(result["constraining_metric"]) == ["voltage", "voltage", "voltage"]

    def test_protection_variants(self):
        config = _make_config()
        df = _make_raw_df(
            constraining_metric=["Fault Current", "BREAKER_REACH", "protection"],
        )
        result = normalize_hosting_capacity(df, config)
        assert list(result["constraining_metric"]) == ["protection", "protection", "protection"]

    def test_unknown_constraint_passthrough(self):
        config = _make_config()
        df = _make_raw_df(constraining_metric=["custom_constraint", "thermal", "voltage"])
        result = normalize_hosting_capacity(df, config)
        assert result["constraining_metric"].iloc[0] == "custom_constraint"

    def test_null_constraint_becomes_none(self):
        config = _make_config()
        df = _make_raw_df(constraining_metric=[None, "thermal", ""])
        result = normalize_hosting_capacity(df, config)
        assert pd.isna(result["constraining_metric"].iloc[0])
        assert pd.isna(result["constraining_metric"].iloc[2])


# ── Remaining capacity computation ──

class TestRemainingCapacity:
    def test_computed_when_missing(self):
        config = _make_config()
        df = _make_raw_df()
        # Remove remaining_capacity_mw if present
        if "remaining_capacity_mw" in df.columns:
            df = df.drop(columns=["remaining_capacity_mw"])
        result = normalize_hosting_capacity(df, config)
        # remaining = hosting - installed - queued = 5 - 1 - 0.5 = 3.5
        assert result["remaining_capacity_mw"].iloc[0] == pytest.approx(3.5)

    def test_not_overwritten_when_present(self):
        config = _make_config()
        df = _make_raw_df(remaining_capacity_mw=[99.0, 88.0, 77.0])
        result = normalize_hosting_capacity(df, config)
        assert result["remaining_capacity_mw"].iloc[0] == pytest.approx(99.0)


# ── Validation ──

class TestValidation:
    def test_drops_rows_missing_feeder_id(self):
        config = _make_config()
        df = _make_raw_df(feeder_id_external=["F001", None, "F003"])
        result = normalize_hosting_capacity(df, config)
        assert len(result) == 2

    def test_empty_df_returns_empty(self):
        config = _make_config()
        df = pd.DataFrame()
        result = normalize_hosting_capacity(df, config)
        assert len(result) == 0

    def test_raw_attributes_preserved(self):
        config = _make_config()
        df = _make_raw_df()
        result = normalize_hosting_capacity(df, config)
        assert "raw_attributes" in result.columns
        attrs = result["raw_attributes"].iloc[0]
        assert isinstance(attrs, dict)
        assert "feeder_id_external" in attrs


# ── Geometry handling ──

class TestGeometry:
    def test_centroid_columns_extracted(self):
        config = _make_config()
        df = _make_raw_df()
        df["_centroid_lat"] = [40.0, 41.0, 42.0]
        df["_centroid_lon"] = [-75.0, -76.0, -77.0]
        df["_geometry_type"] = ["Point", "Point", "Point"]
        result = normalize_hosting_capacity(df, config)
        assert result["centroid_lat"].iloc[0] == pytest.approx(40.0)
        assert result["centroid_lon"].iloc[0] == pytest.approx(-75.0)

    def test_internal_columns_dropped(self):
        config = _make_config()
        df = _make_raw_df()
        df["_internal_col"] = [1, 2, 3]
        result = normalize_hosting_capacity(df, config)
        assert "_internal_col" not in result.columns
