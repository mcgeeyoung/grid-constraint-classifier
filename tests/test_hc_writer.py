"""Tests for app.hc_writer._safe_float (pure function)."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.hc_writer import _safe_float


class TestSafeFloat:
    def test_normal_float(self):
        assert _safe_float(3.14) == pytest.approx(3.14)

    def test_integer(self):
        assert _safe_float(42) == pytest.approx(42.0)

    def test_string_number(self):
        assert _safe_float("3.14") == pytest.approx(3.14)

    def test_none_returns_none(self):
        assert _safe_float(None) is None

    def test_nan_returns_none(self):
        assert _safe_float(float("nan")) is None

    def test_invalid_string_returns_none(self):
        assert _safe_float("not_a_number") is None

    def test_empty_string_returns_none(self):
        assert _safe_float("") is None

    def test_zero(self):
        assert _safe_float(0) == pytest.approx(0.0)

    def test_negative(self):
        assert _safe_float(-5.5) == pytest.approx(-5.5)

    def test_inf(self):
        """Infinity is a valid float."""
        assert _safe_float(float("inf")) == float("inf")
