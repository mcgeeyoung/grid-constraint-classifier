"""Tests for core.profile_utils."""

import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.profile_utils import (
    sanitize_12x24,
    flatten_12x24,
    cosine_similarity,
    elementwise_product_12x24,
    max_merge_12x24,
    profile_summary_stats,
    normalize_min_max,
    severity_tier,
    value_tier,
    compute_overlap_hours,
)


def _make_profile(fill=0.0):
    """Helper: build a 12x24 profile filled with a constant."""
    return {str(m): [fill] * 24 for m in range(1, 13)}


def _make_solar_like():
    """Helper: simple solar-like profile (nonzero hours 7-18)."""
    profile = {}
    for m in range(1, 13):
        row = [0.0] * 24
        for h in range(7, 19):
            row[h] = 0.5 + 0.3 * (1.0 - abs(h - 12) / 6.0)
        profile[str(m)] = row
    return profile


# -- sanitize_12x24 -----------------------------------------------------------

class TestSanitize12x24:
    def test_replaces_nan(self):
        p = _make_profile()
        p["1"][5] = float("nan")
        result = sanitize_12x24(p)
        assert result["1"][5] == 0.0

    def test_replaces_inf(self):
        p = _make_profile()
        p["3"][10] = float("inf")
        p["3"][11] = float("-inf")
        result = sanitize_12x24(p)
        assert result["3"][10] == 0.0
        assert result["3"][11] == 0.0

    def test_preserves_valid_values(self):
        p = _make_profile(0.42)
        result = sanitize_12x24(p)
        assert result["6"][12] == 0.42

    def test_fills_missing_months(self):
        p = {"1": [1.0] * 24}  # Only month 1
        result = sanitize_12x24(p)
        assert len(result) == 12
        assert result["12"] == [0.0] * 24


# -- flatten_12x24 -----------------------------------------------------------

class TestFlatten12x24:
    def test_output_length(self):
        p = _make_profile(1.0)
        vec = flatten_12x24(p)
        assert len(vec) == 288

    def test_ordering(self):
        p = _make_profile()
        p["1"][0] = 0.1
        p["2"][0] = 0.2
        vec = flatten_12x24(p)
        assert vec[0] == 0.1   # month 1, hour 0
        assert vec[24] == 0.2  # month 2, hour 0

    def test_missing_months_zero_filled(self):
        vec = flatten_12x24({})
        assert len(vec) == 288
        assert all(v == 0.0 for v in vec)


# -- cosine_similarity -------------------------------------------------------

class TestCosineSimilarity:
    def test_identical_vectors(self):
        v = [1.0, 2.0, 3.0]
        assert cosine_similarity(v, v) == pytest.approx(1.0, abs=0.001)

    def test_orthogonal_vectors(self):
        a = [1.0, 0.0]
        b = [0.0, 1.0]
        assert cosine_similarity(a, b) == pytest.approx(0.0, abs=0.001)

    def test_zero_vector(self):
        a = [1.0, 2.0]
        b = [0.0, 0.0]
        assert cosine_similarity(a, b) == 0.0

    def test_both_zero_vectors(self):
        assert cosine_similarity([0.0, 0.0], [0.0, 0.0]) == 0.0

    def test_clamped_to_01(self):
        a = [1.0, 0.5]
        b = [1.0, 0.5]
        result = cosine_similarity(a, b)
        assert 0.0 <= result <= 1.0


# -- elementwise_product_12x24 -----------------------------------------------

class TestElementwiseProduct:
    def test_product_with_ones(self):
        p = _make_solar_like()
        ones = _make_profile(1.0)
        result = elementwise_product_12x24(p, ones)
        assert result == p

    def test_product_with_zeros(self):
        p = _make_solar_like()
        zeros = _make_profile(0.0)
        result = elementwise_product_12x24(p, zeros)
        for m_key, row in result.items():
            assert all(v == 0.0 for v in row)


# -- max_merge_12x24 ---------------------------------------------------------

class TestMaxMerge:
    def test_single_profile(self):
        p = _make_solar_like()
        result = max_merge_12x24([p])
        assert result == p

    def test_empty_list(self):
        result = max_merge_12x24([])
        assert len(result) == 12
        for row in result.values():
            assert all(v == 0.0 for v in row)

    def test_takes_max(self):
        a = _make_profile(0.3)
        b = _make_profile(0.7)
        result = max_merge_12x24([a, b])
        for row in result.values():
            assert all(v == 0.7 for v in row)


# -- profile_summary_stats ---------------------------------------------------

class TestProfileSummaryStats:
    def test_peak_detection(self):
        p = _make_profile(0.0)
        p["7"][14] = 0.95  # July at 2pm
        stats = profile_summary_stats(p)
        assert stats["peak_month"] == 7
        assert stats["peak_hour"] == 14
        assert stats["peak_intensity"] == pytest.approx(0.95, abs=0.01)

    def test_constrained_hours(self):
        p = _make_profile(0.5)  # All cells above 0
        stats = profile_summary_stats(p, threshold=0.0)
        assert stats["constrained_hours_pct"] == pytest.approx(1.0)
        assert stats["total_constrained_hours"] > 0

    def test_zero_profile(self):
        p = _make_profile(0.0)
        stats = profile_summary_stats(p, threshold=0.0)
        assert stats["peak_intensity"] == 0.0
        assert stats["constrained_hours_pct"] == 0.0
        assert stats["total_constrained_hours"] == 0


# -- normalize_min_max -------------------------------------------------------

class TestNormalizeMinMax:
    def test_basic(self):
        result = normalize_min_max([0, 5, 10])
        assert result == [0.0, 0.5, 1.0]

    def test_single_value(self):
        result = normalize_min_max([5.0])
        assert result == [0.5]

    def test_empty(self):
        assert normalize_min_max([]) == []

    def test_all_same(self):
        result = normalize_min_max([3.0, 3.0, 3.0])
        assert all(v == 0.5 for v in result)


# -- severity_tier / value_tier -----------------------------------------------

class TestTiers:
    def test_severity_tiers(self):
        assert severity_tier(0.80) == "critical"
        assert severity_tier(0.60) == "elevated"
        assert severity_tier(0.30) == "moderate"
        assert severity_tier(0.10) == "low"

    def test_value_tiers(self):
        assert value_tier(200.0) == "premium"
        assert value_tier(100.0) == "high"
        assert value_tier(50.0) == "moderate"
        assert value_tier(10.0) == "low"


# -- compute_overlap_hours ---------------------------------------------------

class TestComputeOverlapHours:
    def test_full_overlap(self):
        p = _make_profile(1.0)
        hours = compute_overlap_hours(p, p, threshold_a=0.0, threshold_b=0.0)
        # 288 cells * 30.4 days/month ≈ 8760
        assert hours > 8000

    def test_no_overlap(self):
        a = _make_profile(1.0)
        b = _make_profile(0.0)
        hours = compute_overlap_hours(a, b, threshold_a=0.0, threshold_b=0.5)
        assert hours == 0

    def test_dispatchable_none_profile(self):
        a = _make_profile(1.0)
        hours = compute_overlap_hours(a, None, threshold_a=0.0)
        assert hours > 8000

    def test_dispatchable_with_threshold(self):
        a = _make_profile(0.5)
        hours = compute_overlap_hours(a, None, threshold_a=0.6)
        assert hours == 0
