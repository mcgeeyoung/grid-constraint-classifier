"""Cross-link HC utility configs with EIA-861 registry entries.

Matches existing HC utilities (by name similarity) to their EIA IDs, then
updates the utility records with eia_id, utility_type, and regulator_id.

Usage:
  python -m cli.link_eia_utilities
  python -m cli.link_eia_utilities --dry-run
"""

import argparse
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

# Hand-curated EIA ID mappings for HC utilities.
# EIA IDs from https://www.eia.gov/electricity/data/eia861/
# These are stable identifiers that won't change.
EIA_MAPPINGS = {
    "pge": {"eia_id": 14328, "utility_type": "IOU", "state": "CA"},
    "sce": {"eia_id": 17609, "utility_type": "IOU", "state": "CA"},
    "pepco": {"eia_id": 14655, "utility_type": "IOU", "state": "DC"},
    "bge": {"eia_id": 1167, "utility_type": "IOU", "state": "MD"},
    "ace": {"eia_id": 643, "utility_type": "IOU", "state": "NJ"},
    "dpl": {"eia_id": 5027, "utility_type": "IOU", "state": "DE"},
    "comed": {"eia_id": 4110, "utility_type": "IOU", "state": "IL"},
    "peco": {"eia_id": 14612, "utility_type": "IOU", "state": "PA"},
    "coned": {"eia_id": 4226, "utility_type": "IOU", "state": "NY"},
    "nationalgrid": {"eia_id": 13511, "utility_type": "IOU", "state": "NY"},
    "oru": {"eia_id": 14154, "utility_type": "IOU", "state": "NY"},
    "nyseg_rge": {"eia_id": 13573, "utility_type": "IOU", "state": "NY"},  # NYSEG EIA ID; RGE is 16183
    "dte": {"eia_id": 5109, "utility_type": "IOU", "state": "MI"},
    "eversource": {"eia_id": 14725, "utility_type": "IOU", "state": "MA"},  # NSTAR Electric (now Eversource)
    "dominion": {"eia_id": 19876, "utility_type": "IOU", "state": "VA"},
    "xcel_mn": {"eia_id": 13781, "utility_type": "IOU", "state": "MN"},  # Northern States Power
    "xcel_co": {"eia_id": 15466, "utility_type": "IOU", "state": "CO"},  # Public Service Co of Colorado
}


def main():
    parser = argparse.ArgumentParser(description="Cross-link HC utilities with EIA-861")
    parser.add_argument("--dry-run", action="store_true", help="Print matches without writing")
    args = parser.parse_args()

    if args.dry_run:
        print(f"\n{'Code':<15} {'EIA ID':>7} {'Type':<6} {'State':<6} {'Utility Name'}")
        print("-" * 70)
        for code, info in sorted(EIA_MAPPINGS.items()):
            print(f"{code:<15} {info['eia_id']:>7} {info['utility_type']:<6} {info['state']:<6}")
        print(f"\nTotal: {len(EIA_MAPPINGS)} mappings (dry run)\n")
        return

    from app.database import SessionLocal
    from app.models import Utility, Regulator

    session = SessionLocal()
    try:
        # Build regulator lookup
        regulators = {r.state: r.id for r in session.query(Regulator).all()}
        logger.info(f"Found {len(regulators)} regulators in DB")

        updated = 0
        not_found = 0

        for code, info in EIA_MAPPINGS.items():
            util = session.query(Utility).filter(Utility.utility_code == code).first()
            if not util:
                logger.warning(f"Utility {code} not found in DB (not yet ingested?)")
                not_found += 1
                continue

            changed = False

            if util.eia_id != info["eia_id"]:
                util.eia_id = info["eia_id"]
                changed = True

            if util.utility_type != info["utility_type"]:
                util.utility_type = info["utility_type"]
                changed = True

            state = info["state"]
            if util.state != state:
                util.state = state
                changed = True

            if state in regulators and util.regulator_id != regulators[state]:
                util.regulator_id = regulators[state]
                changed = True

            if changed:
                updated += 1
                logger.info(f"Updated {code}: eia_id={info['eia_id']}, type={info['utility_type']}, state={state}")

        session.commit()
        logger.info(f"Done: {updated} updated, {not_found} not found in DB")
        print(f"\nEIA cross-link complete: {updated} utilities updated\n")

    except Exception as e:
        session.rollback()
        logger.error(f"Failed: {e}")
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()
