"""Tests for core.der_profiles."""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.der_profiles import (
    get_der_profile,
    compute_coincidence_factor,
    DER_PROFILES,
    CATEGORY_DEFAULT_CF,
    WATTCARBON_KIND_MAP,
    _SOLAR_PROFILE,
    _WIND_PROFILE,
    _CONSISTENT_PROFILE,
)


# Mock ASSET_KINDS to avoid importing core.der_recommender (which may have heavy deps)
MOCK_ASSET_KINDS = {
    "solar": {"category": "variable", "label": "Solar PV"},
    "wind": {"category": "variable", "label": "Wind"},
    "storage": {"category": "dispatchable", "label": "Battery Storage"},
    "demand_response": {"category": "dispatchable", "label": "Demand Response"},
    "energy_efficiency_eemetered": {"category": "consistent", "label": "EE Metered"},
    "weatherization": {"category": "consistent", "label": "Weatherization"},
    "combined_heat_power": {"category": "consistent", "label": "CHP"},
    "fuel_cell": {"category": "dispatchable", "label": "Fuel Cell"},
}


class TestGetDerProfile:
    def test_solar_returns_profile(self):
        profile = get_der_profile("solar")
        assert profile is not None
        assert len(profile) == 12  # 12 months

    def test_solar_profile_shape(self):
        profile = get_der_profile("solar")
        for month_key, hours in profile.items():
            assert len(hours) == 24, f"Month {month_key} should have 24 hours"

    def test_solar_peaks_midday(self):
        """Solar output should peak around midday (hours 11-13)."""
        profile = get_der_profile("solar")
        for month_key in ["6", "7"]:  # Summer months
            hours = profile[month_key]
            peak_hour = hours.index(max(hours))
            assert 10 <= peak_hour <= 14, f"Month {month_key} peak at hour {peak_hour}"

    def test_solar_zero_at_night(self):
        """Solar output should be 0 during night hours."""
        profile = get_der_profile("solar")
        for month_key, hours in profile.items():
            assert hours[0] == 0.0, f"Month {month_key} hour 0 should be 0"
            assert hours[23] == 0.0, f"Month {month_key} hour 23 should be 0"

    def test_wind_returns_profile(self):
        profile = get_der_profile("wind")
        assert profile is not None
        assert len(profile) == 12

    def test_wind_nonzero_at_night(self):
        """Wind output should be nonzero at all hours."""
        profile = get_der_profile("wind")
        for month_key, hours in profile.items():
            assert all(h > 0 for h in hours), f"Month {month_key} has zero wind"

    def test_storage_returns_none(self):
        """Dispatchable resources have no fixed profile."""
        assert get_der_profile("storage") is None

    def test_demand_response_returns_none(self):
        assert get_der_profile("demand_response") is None

    def test_consistent_profile_flat(self):
        """EE/weatherization should have flat 1.0 profiles."""
        profile = get_der_profile("energy_efficiency_eemetered")
        assert profile is not None
        for month_key, hours in profile.items():
            assert all(h == 1.0 for h in hours)

    def test_unknown_type_returns_none(self):
        assert get_der_profile("nonexistent_type") is None


class TestCoincidenceFactor:
    @patch("core.der_profiles.get_eac_category")
    def test_dispatchable_always_one(self, mock_cat):
        mock_cat.return_value = "dispatchable"
        cf = compute_coincidence_factor("storage", constraint_loadshape=None)
        assert cf == 1.0

    @patch("core.der_profiles.get_eac_category")
    def test_no_loadshape_returns_default(self, mock_cat):
        mock_cat.return_value = "variable"
        cf = compute_coincidence_factor("solar", constraint_loadshape=None)
        assert cf == CATEGORY_DEFAULT_CF["variable"]

    @patch("core.der_profiles.get_eac_category")
    def test_identical_profiles_high_cf(self, mock_cat):
        """Coincidence factor with itself should be ~1.0."""
        mock_cat.return_value = "variable"
        cf = compute_coincidence_factor("solar", constraint_loadshape=_SOLAR_PROFILE)
        assert cf == pytest.approx(1.0, abs=0.01)

    @patch("core.der_profiles.get_eac_category")
    def test_orthogonal_profiles_low_cf(self, mock_cat):
        """Solar vs night-only constraint should have low CF."""
        mock_cat.return_value = "variable"
        # Night-only loadshape: high at night, zero during day
        night_loadshape = {}
        for m in range(1, 13):
            hours = [1.0 if h < 6 or h >= 20 else 0.0 for h in range(24)]
            night_loadshape[str(m)] = hours

        cf = compute_coincidence_factor("solar", constraint_loadshape=night_loadshape)
        assert cf < 0.3  # Very low overlap

    @patch("core.der_profiles.get_eac_category")
    def test_consistent_profile_moderate_cf(self, mock_cat):
        """Consistent (flat) profile vs solar constraint should be moderate."""
        mock_cat.return_value = "consistent"
        cf = compute_coincidence_factor(
            "energy_efficiency_eemetered",
            constraint_loadshape=_SOLAR_PROFILE,
        )
        assert 0.3 < cf < 0.9

    @patch("core.der_profiles.get_eac_category")
    def test_zero_loadshape_returns_default(self, mock_cat):
        """All-zero loadshape should return category default."""
        mock_cat.return_value = "variable"
        zero_loadshape = {str(m): [0.0] * 24 for m in range(1, 13)}
        cf = compute_coincidence_factor("solar", constraint_loadshape=zero_loadshape)
        assert cf == CATEGORY_DEFAULT_CF["variable"]


class TestWattCarbonKindMap:
    def test_solar_maps_correctly(self):
        assert WATTCARBON_KIND_MAP["solar"] == "solar"

    def test_storage_maps_correctly(self):
        assert WATTCARBON_KIND_MAP["storage"] == "storage"

    def test_ee_lighting_maps_to_ee_metered(self):
        assert WATTCARBON_KIND_MAP["energy_efficiency_lighting"] == "energy_efficiency_eemetered"

    def test_electrification_maps_to_weatherization(self):
        assert WATTCARBON_KIND_MAP["electrification_nrel_resstock"] == "weatherization"
        assert WATTCARBON_KIND_MAP["electrification_rewiring_america_deemed"] == "weatherization"
