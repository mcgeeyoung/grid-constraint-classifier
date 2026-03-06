"""
Seed canonical DER profiles into the der_profiles table.

Usage:
  python -m cli.seed_der_profiles
"""

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


# Import canonical profiles from existing code
from core.der_profiles import _SOLAR_PROFILE, _WIND_PROFILE, _CONSISTENT_PROFILE


CANONICAL_PROFILES = [
    {
        "der_type": "solar",
        "eac_category": "variable",
        "profile_source": "canonical",
        "profile_12x24": _SOLAR_PROFILE,
        "is_dispatchable": False,
        "capacity_factor": 0.4,
        "notes": "US-average fixed-tilt solar. Peaks summer afternoon.",
    },
    {
        "der_type": "wind",
        "eac_category": "variable",
        "profile_source": "canonical",
        "profile_12x24": _WIND_PROFILE,
        "is_dispatchable": False,
        "capacity_factor": 0.4,
        "notes": "US-average onshore wind. Higher output at night and winter.",
    },
    {
        "der_type": "storage",
        "eac_category": "dispatchable",
        "profile_source": "canonical",
        "profile_12x24": None,
        "is_dispatchable": True,
        "max_dispatch_hours": 4.0,
        "dispatch_power_mw": 1.0,
        "capacity_factor": 1.0,
        "notes": "4-hour battery storage. Dispatches during constraint hours.",
    },
    {
        "der_type": "demand_response",
        "eac_category": "dispatchable",
        "profile_source": "canonical",
        "profile_12x24": None,
        "is_dispatchable": True,
        "max_dispatch_hours": 2.0,
        "dispatch_power_mw": 1.0,
        "capacity_factor": 1.0,
        "notes": "Demand response. 2-hour event duration.",
    },
    {
        "der_type": "energy_efficiency",
        "eac_category": "consistent",
        "profile_source": "canonical",
        "profile_12x24": _CONSISTENT_PROFILE,
        "is_dispatchable": False,
        "capacity_factor": 0.5,
        "notes": "Energy efficiency measures. Flat reduction profile.",
    },
    {
        "der_type": "weatherization",
        "eac_category": "consistent",
        "profile_source": "canonical",
        "profile_12x24": _CONSISTENT_PROFILE,
        "is_dispatchable": False,
        "capacity_factor": 0.5,
        "notes": "Weatherization/envelope improvements. Flat reduction profile.",
    },
    {
        "der_type": "combined_heat_power",
        "eac_category": "consistent",
        "profile_source": "canonical",
        "profile_12x24": _CONSISTENT_PROFILE,
        "is_dispatchable": False,
        "capacity_factor": 0.5,
        "notes": "Combined heat and power. Baseload operation.",
    },
    {
        "der_type": "fuel_cell",
        "eac_category": "dispatchable",
        "profile_source": "canonical",
        "profile_12x24": None,
        "is_dispatchable": True,
        "max_dispatch_hours": 24.0,
        "dispatch_power_mw": 1.0,
        "capacity_factor": 1.0,
        "notes": "Fuel cell. 24-hour dispatch capability.",
    },
]


def main():
    from app.database import SessionLocal
    from app.models.der_profile import DERProfile

    db = SessionLocal()
    try:
        created = 0
        skipped = 0
        for profile_data in CANONICAL_PROFILES:
            existing = db.query(DERProfile).filter_by(
                der_type=profile_data["der_type"],
                profile_source="canonical",
            ).first()

            if existing:
                logger.info(f"  Skipping {profile_data['der_type']} (already exists)")
                skipped += 1
                continue

            profile = DERProfile(**profile_data)
            db.add(profile)
            created += 1
            logger.info(f"  Created {profile_data['der_type']} ({profile_data['eac_category']})")

        db.commit()
        logger.info(f"Seeded DER profiles: {created} created, {skipped} skipped")

    except Exception as e:
        db.rollback()
        logger.error(f"Failed to seed DER profiles: {e}")
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
