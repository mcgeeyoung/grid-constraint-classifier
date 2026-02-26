"""
Canonical DER output profiles and coincidence factor computation.

Provides 12x24 normalized output profiles for each DER type and computes
the coincidence factor between a DER profile and a constraint loadshape.
"""

import logging
import math
from typing import Optional

logger = logging.getLogger(__name__)

# 12x24 solar profile: normalized [0, 1] output by month and hour.
# Approximate US-average fixed-tilt solar. Peak in summer afternoon.
_SOLAR_PROFILE = {
    "1":  [0, 0, 0, 0, 0, 0, 0, 0.05, 0.20, 0.45, 0.60, 0.70, 0.72, 0.68, 0.55, 0.35, 0.10, 0, 0, 0, 0, 0, 0, 0],
    "2":  [0, 0, 0, 0, 0, 0, 0, 0.10, 0.30, 0.55, 0.70, 0.78, 0.80, 0.75, 0.62, 0.42, 0.18, 0, 0, 0, 0, 0, 0, 0],
    "3":  [0, 0, 0, 0, 0, 0, 0, 0.15, 0.40, 0.62, 0.78, 0.85, 0.87, 0.83, 0.72, 0.52, 0.28, 0.05, 0, 0, 0, 0, 0, 0],
    "4":  [0, 0, 0, 0, 0, 0, 0.05, 0.22, 0.48, 0.70, 0.85, 0.92, 0.94, 0.90, 0.80, 0.62, 0.38, 0.12, 0, 0, 0, 0, 0, 0],
    "5":  [0, 0, 0, 0, 0, 0, 0.08, 0.28, 0.55, 0.78, 0.90, 0.96, 0.98, 0.95, 0.85, 0.68, 0.45, 0.18, 0.02, 0, 0, 0, 0, 0],
    "6":  [0, 0, 0, 0, 0, 0, 0.10, 0.32, 0.58, 0.80, 0.92, 0.98, 1.00, 0.97, 0.88, 0.72, 0.50, 0.22, 0.05, 0, 0, 0, 0, 0],
    "7":  [0, 0, 0, 0, 0, 0, 0.10, 0.30, 0.56, 0.78, 0.91, 0.97, 0.99, 0.96, 0.86, 0.70, 0.48, 0.20, 0.04, 0, 0, 0, 0, 0],
    "8":  [0, 0, 0, 0, 0, 0, 0.06, 0.25, 0.50, 0.73, 0.87, 0.94, 0.96, 0.92, 0.82, 0.65, 0.42, 0.15, 0.01, 0, 0, 0, 0, 0],
    "9":  [0, 0, 0, 0, 0, 0, 0.02, 0.18, 0.42, 0.65, 0.80, 0.88, 0.90, 0.85, 0.74, 0.55, 0.32, 0.08, 0, 0, 0, 0, 0, 0],
    "10": [0, 0, 0, 0, 0, 0, 0, 0.12, 0.35, 0.58, 0.72, 0.80, 0.82, 0.78, 0.65, 0.45, 0.22, 0.02, 0, 0, 0, 0, 0, 0],
    "11": [0, 0, 0, 0, 0, 0, 0, 0.06, 0.25, 0.48, 0.62, 0.72, 0.74, 0.70, 0.57, 0.38, 0.14, 0, 0, 0, 0, 0, 0, 0],
    "12": [0, 0, 0, 0, 0, 0, 0, 0.04, 0.18, 0.42, 0.58, 0.68, 0.70, 0.65, 0.52, 0.32, 0.08, 0, 0, 0, 0, 0, 0, 0],
}

# Wind profile: flatter than solar, slightly higher output at night and in winter.
_WIND_PROFILE = {
    "1":  [0.40, 0.42, 0.44, 0.45, 0.44, 0.42, 0.40, 0.38, 0.35, 0.32, 0.30, 0.28, 0.28, 0.30, 0.32, 0.35, 0.38, 0.40, 0.42, 0.44, 0.45, 0.44, 0.43, 0.42],
    "2":  [0.42, 0.44, 0.45, 0.46, 0.45, 0.43, 0.41, 0.39, 0.36, 0.33, 0.31, 0.29, 0.29, 0.31, 0.33, 0.36, 0.39, 0.41, 0.43, 0.45, 0.46, 0.45, 0.44, 0.43],
    "3":  [0.38, 0.40, 0.42, 0.43, 0.42, 0.40, 0.38, 0.36, 0.34, 0.31, 0.29, 0.27, 0.27, 0.29, 0.31, 0.34, 0.36, 0.38, 0.40, 0.42, 0.43, 0.42, 0.40, 0.39],
    "4":  [0.34, 0.36, 0.38, 0.39, 0.38, 0.36, 0.34, 0.32, 0.30, 0.28, 0.26, 0.25, 0.25, 0.26, 0.28, 0.30, 0.32, 0.34, 0.36, 0.38, 0.39, 0.38, 0.36, 0.35],
    "5":  [0.28, 0.30, 0.32, 0.33, 0.32, 0.30, 0.28, 0.26, 0.25, 0.23, 0.22, 0.21, 0.21, 0.22, 0.23, 0.25, 0.26, 0.28, 0.30, 0.32, 0.33, 0.32, 0.30, 0.29],
    "6":  [0.24, 0.26, 0.28, 0.29, 0.28, 0.26, 0.24, 0.22, 0.21, 0.20, 0.19, 0.18, 0.18, 0.19, 0.20, 0.21, 0.22, 0.24, 0.26, 0.28, 0.29, 0.28, 0.26, 0.25],
    "7":  [0.22, 0.24, 0.26, 0.27, 0.26, 0.24, 0.22, 0.20, 0.19, 0.18, 0.17, 0.16, 0.16, 0.17, 0.18, 0.19, 0.20, 0.22, 0.24, 0.26, 0.27, 0.26, 0.24, 0.23],
    "8":  [0.24, 0.26, 0.28, 0.29, 0.28, 0.26, 0.24, 0.22, 0.21, 0.20, 0.19, 0.18, 0.18, 0.19, 0.20, 0.21, 0.22, 0.24, 0.26, 0.28, 0.29, 0.28, 0.26, 0.25],
    "9":  [0.30, 0.32, 0.34, 0.35, 0.34, 0.32, 0.30, 0.28, 0.26, 0.24, 0.23, 0.22, 0.22, 0.23, 0.24, 0.26, 0.28, 0.30, 0.32, 0.34, 0.35, 0.34, 0.32, 0.31],
    "10": [0.36, 0.38, 0.40, 0.41, 0.40, 0.38, 0.36, 0.34, 0.32, 0.30, 0.28, 0.27, 0.27, 0.28, 0.30, 0.32, 0.34, 0.36, 0.38, 0.40, 0.41, 0.40, 0.38, 0.37],
    "11": [0.38, 0.40, 0.42, 0.43, 0.42, 0.40, 0.38, 0.36, 0.34, 0.31, 0.29, 0.28, 0.28, 0.29, 0.31, 0.34, 0.36, 0.38, 0.40, 0.42, 0.43, 0.42, 0.40, 0.39],
    "12": [0.40, 0.42, 0.44, 0.45, 0.44, 0.42, 0.40, 0.38, 0.35, 0.32, 0.30, 0.28, 0.28, 0.30, 0.32, 0.35, 0.38, 0.40, 0.42, 0.44, 0.45, 0.44, 0.43, 0.42],
}

# Consistent resources (EE, weatherization, CHP): flat profile, always on.
_CONSISTENT_PROFILE = {
    str(m): [1.0] * 24 for m in range(1, 13)
}

# Canonical profiles by DER type
DER_PROFILES: dict[str, dict[str, list[float]]] = {
    "solar": _SOLAR_PROFILE,
    "wind": _WIND_PROFILE,
    "storage": None,  # Dispatchable: CF = 1.0 by definition
    "demand_response": None,  # Dispatchable: CF = 1.0
    "energy_efficiency_eemetered": _CONSISTENT_PROFILE,
    "weatherization": _CONSISTENT_PROFILE,
    "combined_heat_power": _CONSISTENT_PROFILE,
    "fuel_cell": None,  # Dispatchable: CF = 1.0
}

# Category to coincidence default (used when no loadshape available)
CATEGORY_DEFAULT_CF = {
    "dispatchable": 1.0,
    "consistent": 0.5,
    "variable": 0.4,
}


# Map WattCarbon API asset `kind` values to internal der_type keys.
WATTCARBON_KIND_MAP: dict[str, str] = {
    "solar": "solar",
    "storage": "storage",
    "demand_response": "demand_response",
    "energy_efficiency_eemetered": "energy_efficiency_eemetered",
    "energy_efficiency_lighting": "energy_efficiency_eemetered",
    "electrification_nrel_resstock": "weatherization",
    "electrification_rewiring_america_deemed": "weatherization",
}


def get_der_profile(der_type: str) -> Optional[dict[str, list[float]]]:
    """Get the canonical 12x24 output profile for a DER type.

    Returns None for dispatchable types (CF = 1.0 by definition).
    """
    return DER_PROFILES.get(der_type)


def get_eac_category(der_type: str) -> str:
    """Map DER type to EAC category (variable/consistent/dispatchable)."""
    from core.der_recommender import ASSET_KINDS
    info = ASSET_KINDS.get(der_type, {})
    return info.get("category", "variable")


def compute_coincidence_factor(
    der_type: str,
    constraint_loadshape: Optional[dict[str, list[float]]] = None,
) -> float:
    """
    Compute the coincidence factor between a DER output profile and a
    constraint loadshape using cosine similarity.

    Args:
        der_type: DER type key (e.g. "solar", "storage")
        constraint_loadshape: 12x24 dict from PnodeScore or HierarchyScore.
            Format: {"1": [24 floats], ..., "12": [24 floats]}

    Returns:
        Float in [0, 1]. 1.0 = perfect coincidence with constraints.
    """
    category = get_eac_category(der_type)

    # Dispatchable resources dispatch during constraint hours by definition
    if category == "dispatchable":
        return 1.0

    profile = get_der_profile(der_type)
    if profile is None or constraint_loadshape is None:
        return CATEGORY_DEFAULT_CF.get(category, 0.4)

    # Flatten both 12x24 profiles to 288-element vectors
    der_vec = []
    constraint_vec = []
    for month in range(1, 13):
        m_key = str(month)
        der_row = profile.get(m_key, [0.0] * 24)
        constraint_row = constraint_loadshape.get(m_key, [0.0] * 24)
        der_vec.extend(der_row)
        constraint_vec.extend(constraint_row)

    # Cosine similarity
    dot = sum(a * b for a, b in zip(der_vec, constraint_vec))
    mag_a = math.sqrt(sum(a * a for a in der_vec))
    mag_b = math.sqrt(sum(b * b for b in constraint_vec))

    if mag_a < 1e-9 or mag_b < 1e-9:
        return CATEGORY_DEFAULT_CF.get(category, 0.4)

    similarity = dot / (mag_a * mag_b)
    return round(max(0.0, min(1.0, similarity)), 4)
