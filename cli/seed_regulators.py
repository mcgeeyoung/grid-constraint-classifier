"""Seed the regulators table from data/seed/regulators.json.

Usage:
  python -m cli.seed_regulators
  python -m cli.seed_regulators --dry-run
"""

import argparse
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.models import Regulator
from app.database import SessionLocal

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

SEED_FILE = Path(__file__).resolve().parent.parent / "data" / "seed" / "regulators.json"


def main():
    parser = argparse.ArgumentParser(description="Seed regulators table")
    parser.add_argument("--dry-run", action="store_true", help="Print without writing")
    args = parser.parse_args()

    with open(SEED_FILE) as f:
        regulators = json.load(f)

    logger.info(f"Loaded {len(regulators)} regulators from {SEED_FILE.name}")

    if args.dry_run:
        print(f"\n{'State':<6} {'Abbrev':<8} {'Name':<50} {'eFiling Type'}")
        print("-" * 80)
        for r in regulators:
            etype = r.get("efiling_type") or "-"
            abbrev = r.get("abbreviation") or "-"
            print(f"{r['state']:<6} {abbrev:<8} {r['name']:<50} {etype}")
        print(f"\nTotal: {len(regulators)} regulators (dry run)\n")
        return

    session = SessionLocal()
    try:
        created = 0
        updated = 0
        for r in regulators:
            existing = session.query(Regulator).filter_by(state=r["state"]).first()
            if existing:
                # Update fields
                for key in ("name", "abbreviation", "website", "efiling_url",
                            "efiling_type", "notes"):
                    if key in r and r[key] is not None:
                        setattr(existing, key, r[key])
                if "api_available" in r:
                    existing.api_available = r["api_available"]
                updated += 1
            else:
                reg = Regulator(
                    state=r["state"],
                    name=r["name"],
                    abbreviation=r.get("abbreviation"),
                    website=r.get("website"),
                    efiling_url=r.get("efiling_url"),
                    efiling_type=r.get("efiling_type"),
                    api_available=r.get("api_available", False),
                    notes=r.get("notes"),
                )
                session.add(reg)
                created += 1

        session.commit()
        logger.info(f"Done: {created} created, {updated} updated")
    except Exception as e:
        session.rollback()
        logger.error(f"Failed: {e}")
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()
