#!/usr/bin/env python3
"""
Backfill substation coordinates from GRIP ArcGIS data.

One-time CLI to:
1. Force-fetch GRIP substation data (getting lat/lon from ArcGIS geometry)
2. Update existing substation records with lat/lon
3. Run backfill_substation_zones() to spatially link substations to zones
4. Compute and write hierarchy scores

Usage:
    python -m cli.backfill_substations
    python -m cli.backfill_substations --skip-fetch   # Use existing CSV
    python -m cli.backfill_substations --dry-run       # Preview without DB writes
"""

import argparse
import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(
        description="Backfill substation lat/lon from GRIP ArcGIS and link to zones"
    )
    parser.add_argument(
        "--skip-fetch", action="store_true",
        help="Skip re-fetching GRIP data (use existing CSV)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Preview changes without writing to DB",
    )
    parser.add_argument(
        "--iso", type=str, default="caiso",
        help="ISO to backfill (default: caiso, currently only GRIP data for CAISO)",
    )

    args = parser.parse_args()

    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    iso_id = args.iso.lower()
    data_dir = PROJECT_ROOT / "data"
    grip_cache = data_dir / iso_id / "grip_substations.csv"

    # Step 1: Fetch GRIP data with coordinates
    if not args.skip_fetch:
        logger.info("Step 1: Fetching GRIP substation data from ArcGIS (force=True)...")
        from scraping.grip_fetcher import fetch_grip_substations

        grip_df = fetch_grip_substations(cache_path=grip_cache, force=True)
        logger.info(
            f"  Fetched {len(grip_df)} bank records, "
            f"{grip_df['sub_clean'].nunique()} unique substations"
        )

        # Report coordinate coverage
        has_coords = grip_df["lat"].notna().sum()
        logger.info(f"  Coordinates: {has_coords}/{len(grip_df)} records have lat/lon")
    else:
        logger.info("Step 1: Skipping fetch (using existing CSV)")
        if not grip_cache.exists():
            logger.error(f"  CSV not found: {grip_cache}")
            sys.exit(1)
        import pandas as pd
        grip_df = pd.read_csv(grip_cache)
        has_coords = grip_df["lat"].notna().sum() if "lat" in grip_df.columns else 0
        logger.info(f"  Loaded {len(grip_df)} records, {has_coords} with coordinates")

    if args.dry_run:
        logger.info("Dry run: would update DB with fetched data. Exiting.")
        return

    # Step 2: Get a PipelineWriter and update substation records
    logger.info("Step 2: Updating substation records with lat/lon...")
    try:
        from adapters.registry import get_adapter
        from app.pipeline_writer import get_pipeline_writer

        adapter = get_adapter(iso_id, data_dir=data_dir)
        writer = get_pipeline_writer(iso_id, adapter)

        if not writer:
            logger.error("  Database not available. Cannot backfill.")
            sys.exit(1)

        # Ensure ISO exists
        writer._ensure_iso_and_zones()

        # Write/update substations from refreshed CSV
        writer.write_substations(grip_cache)
    except Exception as e:
        logger.error(f"  Failed to update substations: {e}")
        sys.exit(1)

    # Step 3: Spatial join (link substations to zones and nearest pnodes)
    logger.info("Step 3: Running spatial backfill (zones + nearest pnodes)...")
    try:
        writer.backfill_substation_zones()
    except Exception as e:
        logger.error(f"  Spatial backfill failed: {e}")
        sys.exit(1)

    # Step 4: Compute and write hierarchy scores
    logger.info("Step 4: Computing hierarchy scores...")
    try:
        from core.hierarchy_scorer import compute_all_hierarchy_scores
        from app.models import PipelineRun

        # Find the latest completed pipeline run for this ISO
        latest_run = (
            writer.db.query(PipelineRun)
            .filter(
                PipelineRun.iso_id == writer._iso.id,
                PipelineRun.status == "completed",
            )
            .order_by(PipelineRun.completed_at.desc())
            .first()
        )

        if not latest_run:
            logger.warning("  No completed pipeline run found. Skipping hierarchy scores.")
        else:
            logger.info(f"  Using pipeline run #{latest_run.id}")
            scores = compute_all_hierarchy_scores(
                writer.db, latest_run.id, writer._iso.id,
            )

            if scores:
                # Create a temporary run reference for writing scores
                # (reuse the latest run since this is a backfill)
                writer._run = latest_run
                writer.write_hierarchy_scores(scores)
                logger.info(f"  Wrote {len(scores)} hierarchy scores")
            else:
                logger.info("  No hierarchy scores computed (no data)")
    except Exception as e:
        logger.error(f"  Hierarchy scoring failed: {e}")

    # Summary
    logger.info("")
    logger.info("=" * 60)
    logger.info("Backfill complete!")

    from app.models import Substation
    total = writer.db.query(Substation).filter(
        Substation.iso_id == writer._iso.id,
    ).count()
    with_coords = writer.db.query(Substation).filter(
        Substation.iso_id == writer._iso.id,
        Substation.lat.isnot(None),
    ).count()
    with_zones = writer.db.query(Substation).filter(
        Substation.iso_id == writer._iso.id,
        Substation.zone_id.isnot(None),
    ).count()
    with_pnodes = writer.db.query(Substation).filter(
        Substation.iso_id == writer._iso.id,
        Substation.nearest_pnode_id.isnot(None),
    ).count()

    logger.info(f"  Total substations:  {total}")
    logger.info(f"  With coordinates:   {with_coords}")
    logger.info(f"  Linked to zones:    {with_zones}")
    logger.info(f"  Linked to pnodes:   {with_pnodes}")
    logger.info("=" * 60)

    writer.close()


if __name__ == "__main__":
    main()
