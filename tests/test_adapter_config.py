"""Tests for adapter configuration loading (ISOConfig, UtilityHCConfig)."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from adapters.base import ISOConfig
from adapters.hosting_capacity.base import UtilityHCConfig

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class TestISOConfigFromYaml:
    """Test loading real YAML ISO configs."""

    @pytest.fixture()
    def pjm_config(self):
        yaml_path = PROJECT_ROOT / "adapters" / "configs" / "pjm.yaml"
        if not yaml_path.exists():
            pytest.skip("pjm.yaml not found")
        return ISOConfig.from_yaml(yaml_path)

    def test_iso_id(self, pjm_config):
        assert pjm_config.iso_id == "pjm"

    def test_iso_name(self, pjm_config):
        assert pjm_config.iso_name == "PJM Interconnection"

    def test_peak_hours_is_set(self, pjm_config):
        assert isinstance(pjm_config.peak_hours, set)
        assert 7 in pjm_config.peak_hours
        assert 22 in pjm_config.peak_hours
        assert 6 not in pjm_config.peak_hours

    def test_peak_hours_range_parsing(self, pjm_config):
        """PJM config uses start/end notation for peak hours."""
        assert len(pjm_config.peak_hours) == 16  # 7 through 22

    def test_zones_loaded(self, pjm_config):
        assert len(pjm_config.zones) > 0
        assert "DOM" in pjm_config.zones
        assert "PSEG" in pjm_config.zones

    def test_zone_has_centroid(self, pjm_config):
        dom = pjm_config.zones["DOM"]
        assert "centroid_lat" in dom
        assert "centroid_lon" in dom
        assert 35 < dom["centroid_lat"] < 40
        assert -80 < dom["centroid_lon"] < -76

    def test_validation_zones(self, pjm_config):
        assert "DOM" in pjm_config.validation_zones
        assert pjm_config.validation_zones["DOM"] == "transmission"

    def test_rto_aggregates(self, pjm_config):
        assert "PJM-RTO" in pjm_config.rto_aggregates

    def test_map_center(self, pjm_config):
        lat, lon = pjm_config.map_center
        assert 35 < lat < 45
        assert -85 < lon < -70

    def test_get_zone_centroids(self, pjm_config):
        centroids = pjm_config.get_zone_centroids()
        assert "DOM" in centroids
        assert "lat" in centroids["DOM"]
        assert "lon" in centroids["DOM"]
        assert "name" in centroids["DOM"]


class TestUtilityHCConfigFromYaml:
    """Test loading real YAML hosting capacity configs."""

    @pytest.fixture()
    def duke_config(self):
        yaml_path = (
            PROJECT_ROOT / "adapters" / "hosting_capacity" / "configs" / "duke.yaml"
        )
        if not yaml_path.exists():
            pytest.skip("duke.yaml not found")
        return UtilityHCConfig.from_yaml(yaml_path)

    def test_utility_code(self, duke_config):
        assert duke_config.utility_code == "duke"

    def test_capacity_unit(self, duke_config):
        assert duke_config.capacity_unit == "kw"

    def test_field_map_populated(self, duke_config):
        assert len(duke_config.field_map) > 0
        assert "FEEDER_ID" in duke_config.field_map
        assert duke_config.field_map["FEEDER_ID"] == "feeder_id_external"

    def test_service_url(self, duke_config):
        assert duke_config.service_url is not None
        assert "duke-energy.com" in duke_config.service_url

    def test_states(self, duke_config):
        assert "NC" in duke_config.states
        assert "SC" in duke_config.states

    def test_data_source_type(self, duke_config):
        assert duke_config.data_source_type in (
            "arcgis_feature", "arcgis_map", "exelon", "custom", "unavailable",
        )
