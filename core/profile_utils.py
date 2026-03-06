"""
12x24 profile math utilities.

Functions for normalizing, flattening, and computing similarity between
12x24 (month x hour) profiles used throughout the constraint profile system.
"""

import math
from typing import Optional


def sanitize_12x24(profile: dict[str, list[float]]) -> dict[str, list[float]]:
    """Replace NaN/Inf values with 0.0 in a 12x24 profile.

    PostgreSQL JSON rejects NaN, so this must be called before persisting.
    """
    clean = {}
    for month in range(1, 13):
        m_key = str(month)
        row = profile.get(m_key, [0.0] * 24)
        clean[m_key] = [0.0 if (math.isnan(v) or math.isinf(v)) else v for v in row]
    return clean


def flatten_12x24(profile: dict[str, list[float]]) -> list[float]:
    """Flatten a 12x24 profile dict to a 288-element vector.

    Args:
        profile: {"1": [24 floats], ..., "12": [24 floats]}

    Returns:
        List of 288 floats (month 1 hour 0, month 1 hour 1, ..., month 12 hour 23)
    """
    vec = []
    for month in range(1, 13):
        row = profile.get(str(month), [0.0] * 24)
        vec.extend(row)
    return vec


def cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    """Compute cosine similarity between two vectors.

    Returns:
        Float in [0, 1]. Returns 0 if either vector is zero.
    """
    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    mag_a = math.sqrt(sum(a * a for a in vec_a))
    mag_b = math.sqrt(sum(b * b for b in vec_b))

    if mag_a < 1e-9 or mag_b < 1e-9:
        return 0.0

    return max(0.0, min(1.0, dot / (mag_a * mag_b)))


def elementwise_product_12x24(
    profile_a: dict[str, list[float]],
    profile_b: dict[str, list[float]],
) -> dict[str, list[float]]:
    """Compute element-wise product of two 12x24 profiles.

    Used for overlap visualization (constraint x DER output).
    """
    result = {}
    for month in range(1, 13):
        m_key = str(month)
        row_a = profile_a.get(m_key, [0.0] * 24)
        row_b = profile_b.get(m_key, [0.0] * 24)
        result[m_key] = [a * b for a, b in zip(row_a, row_b)]
    return result


def max_merge_12x24(profiles: list[dict[str, list[float]]]) -> dict[str, list[float]]:
    """Merge multiple 12x24 profiles by taking the max at each cell.

    Used for composite profiles (combining constraint types at a location).
    """
    if not profiles:
        return {str(m): [0.0] * 24 for m in range(1, 13)}

    result = {}
    for month in range(1, 13):
        m_key = str(month)
        rows = [p.get(m_key, [0.0] * 24) for p in profiles]
        result[m_key] = [max(vals) for vals in zip(*rows)]
    return result


def profile_summary_stats(
    profile: dict[str, list[float]],
    threshold: float = 0.0,
) -> dict:
    """Compute summary statistics for a 12x24 profile.

    Args:
        profile: 12x24 profile dict
        threshold: value above which an hour is considered "constrained"

    Returns:
        Dict with peak_intensity, peak_month, peak_hour, mean_intensity,
        total_constrained_hours, constrained_hours_pct
    """
    peak_intensity = 0.0
    peak_month = 1
    peak_hour = 0
    total_value = 0.0
    total_cells = 0
    constrained_cells = 0

    for month in range(1, 13):
        m_key = str(month)
        row = profile.get(m_key, [0.0] * 24)
        for hour, val in enumerate(row):
            total_value += val
            total_cells += 1
            if val > threshold:
                constrained_cells += 1
            if val > peak_intensity:
                peak_intensity = val
                peak_month = month
                peak_hour = hour

    mean_intensity = total_value / total_cells if total_cells > 0 else 0.0
    constrained_hours_pct = constrained_cells / total_cells if total_cells > 0 else 0.0

    # Scale constrained cells to approximate yearly hours
    # Each cell represents ~30 days of that hour, so total constrained hours
    # is constrained_cells * (365/12) ≈ constrained_cells * 30.4
    total_constrained_hours = int(constrained_cells * (365.0 / 12.0))

    return {
        "peak_intensity": round(peak_intensity, 4),
        "peak_month": peak_month,
        "peak_hour": peak_hour,
        "mean_intensity": round(mean_intensity, 4),
        "total_constrained_hours": total_constrained_hours,
        "constrained_hours_pct": round(constrained_hours_pct, 4),
    }


def normalize_min_max(values: list[float]) -> list[float]:
    """Min-max normalize a list of values to [0, 1]."""
    if not values:
        return []
    min_v = min(values)
    max_v = max(values)
    range_v = max_v - min_v
    if range_v < 1e-9:
        return [0.5] * len(values)
    return [(v - min_v) / range_v for v in values]


def severity_tier(score: float) -> str:
    """Map a severity score (0-1) to a tier label."""
    if score >= 0.75:
        return "critical"
    elif score >= 0.50:
        return "elevated"
    elif score >= 0.25:
        return "moderate"
    else:
        return "low"


def value_tier(value_per_kw_year: float) -> str:
    """Map a $/kW-yr value to a tier label."""
    if value_per_kw_year >= 150.0:
        return "premium"
    elif value_per_kw_year >= 80.0:
        return "high"
    elif value_per_kw_year >= 30.0:
        return "moderate"
    else:
        return "low"


def compute_overlap_hours(
    profile_a: dict[str, list[float]],
    profile_b: Optional[dict[str, list[float]]],
    threshold_a: float = 0.0,
    threshold_b: float = 0.0,
) -> int:
    """Count month-hour slots where both profiles exceed their thresholds.

    For dispatchable DERs (profile_b is None), returns the count of
    constrained hours in profile_a.
    """
    count = 0
    for month in range(1, 13):
        m_key = str(month)
        row_a = profile_a.get(m_key, [0.0] * 24)
        if profile_b is None:
            # Dispatchable: overlap with all constrained hours
            count += sum(1 for v in row_a if v > threshold_a)
        else:
            row_b = profile_b.get(m_key, [0.0] * 24)
            count += sum(1 for a, b in zip(row_a, row_b)
                         if a > threshold_a and b > threshold_b)

    # Scale to yearly hours (each cell ≈ 30.4 days)
    return int(count * (365.0 / 12.0))
