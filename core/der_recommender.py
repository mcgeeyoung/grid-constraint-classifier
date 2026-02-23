"""
DER deployment recommendation engine.

Maps grid constraint classifications to optimal DER strategies,
using WattCarbon's verified EAC attribute categories and asset kinds.

WattCarbon EAC categories:
  - variable: solar, wind (weather-dependent output)
  - consistent: energy efficiency, weatherization (steady reduction)
  - dispatchable: battery storage, demand response (controllable, grid-responsive)

ISO-agnostic: works with classification output from any ISO.
"""

import logging
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

# WattCarbon asset kind identifiers (from WEATS registry)
ASSET_KINDS = {
    "solar": {"category": "variable", "label": "Solar PV"},
    "wind": {"category": "variable", "label": "Wind"},
    "storage": {"category": "dispatchable", "label": "Battery Storage"},
    "demand_response": {"category": "dispatchable", "label": "Demand Response"},
    "energy_efficiency_eemetered": {"category": "consistent", "label": "Energy Efficiency (Metered)"},
    "weatherization": {"category": "consistent", "label": "Weatherization"},
    "combined_heat_power": {"category": "consistent", "label": "Combined Heat & Power"},
    "fuel_cell": {"category": "dispatchable", "label": "Fuel Cell"},
}

# Constraint type -> DER strategy mapping
DER_STRATEGIES = {
    "transmission": {
        "rationale": (
            "Transmission-constrained zones have flow limits on power lines. "
            "Dispatchable resources reduce peak flows by providing local supply "
            "or reducing demand during congestion events. Consistent resources "
            "lower baseline load, reducing the magnitude of peak flows."
        ),
        "primary": {
            "category": "dispatchable",
            "assets": ["storage", "demand_response"],
            "reason": "Dispatches during congestion events to reduce line loading",
        },
        "secondary": {
            "category": "consistent",
            "assets": ["energy_efficiency_eemetered", "weatherization"],
            "reason": "Reduces baseline load, lowering chronic transmission stress",
        },
        "tertiary": {
            "category": "variable",
            "assets": ["solar"],
            "reason": "Adds local generation (value depends on coincidence with peak congestion)",
        },
    },
    "generation": {
        "rationale": (
            "Generation-constrained zones lack sufficient local supply. "
            "Consistent resources reduce demand permanently, easing the supply gap. "
            "Variable resources add local generation capacity."
        ),
        "primary": {
            "category": "consistent",
            "assets": ["energy_efficiency_eemetered", "weatherization", "combined_heat_power"],
            "reason": "Permanently reduces demand, closing the local supply gap",
        },
        "secondary": {
            "category": "variable",
            "assets": ["solar", "wind"],
            "reason": "Adds local generation to offset imports",
        },
        "tertiary": {
            "category": "dispatchable",
            "assets": ["storage", "demand_response"],
            "reason": "Provides capacity during generation shortfalls",
        },
    },
    "both": {
        "rationale": (
            "Zones with both transmission and generation constraints benefit "
            "from a diversified DER portfolio. Dispatchable resources handle "
            "acute congestion events while consistent resources address "
            "the structural supply deficit."
        ),
        "primary": {
            "category": "dispatchable",
            "assets": ["storage", "demand_response"],
            "reason": "Addresses acute congestion and generation shortfalls",
        },
        "secondary": {
            "category": "consistent",
            "assets": ["energy_efficiency_eemetered", "weatherization"],
            "reason": "Reduces chronic load, easing both transmission and generation stress",
        },
        "tertiary": {
            "category": "variable",
            "assets": ["solar"],
            "reason": "Adds local supply during daylight hours",
        },
    },
    "unconstrained": {
        "rationale": (
            "Unconstrained zones have adequate transmission and generation. "
            "Consistent resources provide long-term value through load reduction. "
            "DER investment priority is lower here relative to constrained zones."
        ),
        "primary": {
            "category": "consistent",
            "assets": ["energy_efficiency_eemetered"],
            "reason": "Cost-effective load reduction with steady EAC generation",
        },
        "secondary": {
            "category": "variable",
            "assets": ["solar"],
            "reason": "Clean energy addition with moderate grid benefit",
        },
        "tertiary": None,
    },
}


def recommend_ders(
    classification_df: pd.DataFrame,
    lmp_df: Optional[pd.DataFrame] = None,
) -> list[dict]:
    """
    Generate DER recommendations for each classified zone.

    Args:
        classification_df: Output of classify_zones() with columns:
            zone, classification, transmission_score, generation_score,
            avg_abs_congestion, congested_hours_pct
        lmp_df: Raw LMP data (optional, for computing congestion value)

    Returns:
        List of recommendation dicts, one per zone.
    """
    recommendations = []

    for _, row in classification_df.iterrows():
        zone = row["zone"]
        cls = row["classification"]
        strategy = DER_STRATEGIES.get(cls, DER_STRATEGIES["unconstrained"])

        # Congestion economics
        avg_congestion_cost = row.get("avg_abs_congestion", 0)
        congested_hours_pct = row.get("congested_hours_pct", 0)
        n_hours = row.get("n_hours", 8760)
        annual_constrained_hours = int(congested_hours_pct * n_hours)

        # Build asset recommendations with WattCarbon metadata
        primary_assets = []
        for asset_id in strategy["primary"]["assets"]:
            asset_info = ASSET_KINDS[asset_id]
            primary_assets.append({
                "asset_kind": asset_id,
                "label": asset_info["label"],
                "eac_category": asset_info["category"],
                "priority": "primary",
            })

        secondary_assets = []
        for asset_id in strategy["secondary"]["assets"]:
            asset_info = ASSET_KINDS[asset_id]
            secondary_assets.append({
                "asset_kind": asset_id,
                "label": asset_info["label"],
                "eac_category": asset_info["category"],
                "priority": "secondary",
            })

        tertiary_assets = []
        if strategy.get("tertiary"):
            for asset_id in strategy["tertiary"]["assets"]:
                asset_info = ASSET_KINDS[asset_id]
                tertiary_assets.append({
                    "asset_kind": asset_id,
                    "label": asset_info["label"],
                    "eac_category": asset_info["category"],
                    "priority": "tertiary",
                })

        rec = {
            "zone": zone,
            "classification": cls,
            "transmission_score": round(row["transmission_score"], 3),
            "generation_score": round(row["generation_score"], 3),
            "rationale": strategy["rationale"],
            "congestion_value_per_mwh": round(avg_congestion_cost, 2),
            "annual_constrained_hours": annual_constrained_hours,
            "primary_recommendation": {
                "category": strategy["primary"]["category"],
                "reason": strategy["primary"]["reason"],
                "assets": primary_assets,
            },
            "secondary_recommendation": {
                "category": strategy["secondary"]["category"],
                "reason": strategy["secondary"]["reason"],
                "assets": secondary_assets,
            },
        }

        if tertiary_assets:
            rec["tertiary_recommendation"] = {
                "category": strategy["tertiary"]["category"],
                "reason": strategy["tertiary"]["reason"],
                "assets": tertiary_assets,
            }

        recommendations.append(rec)

    logger.info(f"Generated DER recommendations for {len(recommendations)} zones")
    return recommendations


def format_recommendation_text(rec: dict) -> str:
    """Format a single zone recommendation as readable text."""
    lines = [
        f"Zone: {rec['zone']} ({rec['classification'].upper()})",
        f"  Transmission score: {rec['transmission_score']:.3f}  |  Generation score: {rec['generation_score']:.3f}",
        f"  Congestion cost: ${rec['congestion_value_per_mwh']:.2f}/MWh  |  Constrained hours: {rec['annual_constrained_hours']}/yr",
        f"",
        f"  Primary DERs ({rec['primary_recommendation']['category']}):",
    ]
    for a in rec["primary_recommendation"]["assets"]:
        lines.append(f"    - {a['label']} [{a['asset_kind']}]")
    lines.append(f"    Reason: {rec['primary_recommendation']['reason']}")

    lines.append(f"  Secondary DERs ({rec['secondary_recommendation']['category']}):")
    for a in rec["secondary_recommendation"]["assets"]:
        lines.append(f"    - {a['label']} [{a['asset_kind']}]")
    lines.append(f"    Reason: {rec['secondary_recommendation']['reason']}")

    if rec.get("tertiary_recommendation"):
        lines.append(f"  Tertiary DERs ({rec['tertiary_recommendation']['category']}):")
        for a in rec["tertiary_recommendation"]["assets"]:
            lines.append(f"    - {a['label']} [{a['asset_kind']}]")
        lines.append(f"    Reason: {rec['tertiary_recommendation']['reason']}")

    return "\n".join(lines)
