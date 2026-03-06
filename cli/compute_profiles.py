"""
Compute constraint profiles CLI.

Usage:
  python -m cli.compute_profiles --iso caiso --year 2024
  python -m cli.compute_profiles --iso all --year 2024
  python -m cli.compute_profiles --iso caiso --year 2024 --only congestion
  python -m cli.compute_profiles --iso caiso --year 2024 --only loading
  python -m cli.compute_profiles --recompute-intersections
  python -m cli.compute_profiles --recompute-stacks
  python -m cli.compute_profiles --link-annotations
  python -m cli.compute_profiles --full
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


def main():
    parser = argparse.ArgumentParser(
        description="Compute constraint profiles, intersections, and value stacks",
    )
    parser.add_argument(
        "--iso",
        help="ISO code (e.g., caiso) or 'all' for all ISOs",
    )
    parser.add_argument(
        "--year", type=int, default=2024,
        help="Period year (default: 2024)",
    )
    parser.add_argument(
        "--only",
        choices=["congestion", "loading", "capacity", "import_stress"],
        help="Only run a specific profile builder",
    )
    parser.add_argument(
        "--recompute-intersections", action="store_true",
        help="Recompute intersections for existing profiles",
    )
    parser.add_argument(
        "--recompute-stacks", action="store_true",
        help="Recompute value stacks for existing intersections",
    )
    parser.add_argument(
        "--link-annotations", action="store_true",
        help="Link regulatory annotations to existing profiles",
    )
    parser.add_argument(
        "--full", action="store_true",
        help="Run full pipeline (all builders + intersections + stacks + annotations)",
    )
    parser.add_argument(
        "--skip-intersections", action="store_true",
        help="Skip intersection computation",
    )
    parser.add_argument(
        "--skip-stacks", action="store_true",
        help="Skip value stack computation",
    )
    parser.add_argument(
        "--skip-annotations", action="store_true",
        help="Skip annotation linking",
    )

    args = parser.parse_args()

    if not any([args.iso, args.full, args.recompute_intersections,
                args.recompute_stacks, args.link_annotations]):
        parser.print_help()
        sys.exit(1)

    from app.database import SessionLocal
    from core.profile_engine import (
        run_full_pipeline,
        compute_intersections,
        compute_value_stacks,
        link_annotations,
        refresh_materialized_views,
    )
    from app.models.computation_run import ComputationRun

    db = SessionLocal()
    try:
        if args.full or args.iso:
            iso_code = None if args.iso == "all" else args.iso
            run = run_full_pipeline(
                db,
                iso_code=iso_code,
                year=args.year,
                only=args.only,
                skip_intersections=args.skip_intersections,
                skip_stacks=args.skip_stacks,
                skip_annotations=args.skip_annotations,
            )
            logger.info(f"Run #{run.id}: {run.status} ({run.metrics_json})")

        elif args.recompute_intersections:
            # Find the latest successful run
            run = (
                db.query(ComputationRun)
                .filter_by(status="success")
                .order_by(ComputationRun.completed_at.desc())
                .first()
            )
            if not run:
                logger.error("No successful computation run found")
                sys.exit(1)
            count = compute_intersections(db, run)
            db.commit()
            logger.info(f"Recomputed {count} intersections")

        elif args.recompute_stacks:
            run = (
                db.query(ComputationRun)
                .filter_by(status="success")
                .order_by(ComputationRun.completed_at.desc())
                .first()
            )
            if not run:
                logger.error("No successful computation run found")
                sys.exit(1)
            count = compute_value_stacks(db, run)
            db.commit()
            logger.info(f"Recomputed {count} value stacks")

        elif args.link_annotations:
            run = (
                db.query(ComputationRun)
                .filter_by(status="success")
                .order_by(ComputationRun.completed_at.desc())
                .first()
            )
            if not run:
                logger.error("No successful computation run found")
                sys.exit(1)
            count = link_annotations(db, run)
            db.commit()
            logger.info(f"Linked {count} annotations")

        refresh_materialized_views(db)

    except Exception as e:
        db.rollback()
        logger.error(f"Failed: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
