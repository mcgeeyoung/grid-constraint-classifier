"""Tests for core.geo_resolver.haversine_km (pure function, no DB)."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.geo_resolver import haversine_km


class TestHaversineKm:
    def test_same_point_is_zero(self):
        assert haversine_km(40.0, -74.0, 40.0, -74.0) == pytest.approx(0.0, abs=0.01)

    def test_nyc_to_la(self):
        """NYC (40.7128, -74.0060) to LA (34.0522, -118.2437) ~ 3,944 km."""
        dist = haversine_km(40.7128, -74.0060, 34.0522, -118.2437)
        assert 3900 < dist < 4000

    def test_london_to_paris(self):
        """London (51.5074, -0.1278) to Paris (48.8566, 2.3522) ~ 344 km."""
        dist = haversine_km(51.5074, -0.1278, 48.8566, 2.3522)
        assert 340 < dist < 350

    def test_symmetric(self):
        d1 = haversine_km(40.0, -74.0, 34.0, -118.0)
        d2 = haversine_km(34.0, -118.0, 40.0, -74.0)
        assert d1 == pytest.approx(d2, abs=0.01)

    def test_antipodal_points(self):
        """Opposite sides of the earth ~ 20,015 km (half circumference)."""
        dist = haversine_km(0.0, 0.0, 0.0, 180.0)
        assert 20000 < dist < 20100

    def test_poles(self):
        """North pole to south pole ~ 20,015 km."""
        dist = haversine_km(90.0, 0.0, -90.0, 0.0)
        assert 20000 < dist < 20100

    def test_short_distance(self):
        """Two nearby points should give a small distance."""
        dist = haversine_km(40.0000, -74.0000, 40.0010, -74.0010)
        assert dist < 1.0  # Less than 1 km
