"""
Seed substations and feeders from hosting capacity records.

Strategy: HC records come from utilities outside California (DTE, Xcel MN/CO, NYSEG).
Existing substations are California-only (PG&E/SCE). Instead of spatial matching,
create new substations from HC substation_name groupings, then create feeders.

Steps:
  1. Map each HC utility_id to an ISO via utilities.iso_id
  2. Group HC records by (utility_id, substation_name) to create substations
  3. Create feeders under those substations from distinct feeder_names
  4. Backfill HC records with substation_id and feeder_id

Usage:
  python -m cli.seed_feeders_from_hc [--batch-size 5000] [--dry-run]
"""

import argparse
import logging
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# Manual ISO overrides for utilities missing iso_id
ISO_OVERRIDES = {
    # Xcel CO (Public Service Company of Colorado) -> PSCO
    3429: "PSCO",
}


def _parse_substation_prefix(feeder_name: str) -> str:
    """Extract substation prefix from feeder names like 'ACME 9488' or 'ALNPK1145'.

    Returns the alpha prefix before the numeric suffix.
    """
    m = re.match(r"^([A-Za-z]+)", feeder_name.strip())
    return m.group(1).upper() if m else "UNKNOWN"


def main():
    parser = argparse.ArgumentParser(description="Seed feeders from HC records")
    parser.add_argument("--batch-size", type=int, default=5000,
                        help="Commit batch size (default: 5000)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Report stats without writing to DB")
    args = parser.parse_args()

    from sqlalchemy import text, func
    from app.database import SessionLocal
    from app.models.substation import Substation
    from app.models.feeder import Feeder
    from app.models.iso import ISO

    db = SessionLocal()
    try:
        # Step 1: Resolve ISO for each utility
        logger.info("Resolving ISO for each HC utility...")
        utility_rows = db.execute(text("""
            SELECT DISTINCT hc.utility_id, u.utility_name, u.iso_id
            FROM hosting_capacity_records hc
            JOIN utilities u ON u.id = hc.utility_id
            WHERE hc.feeder_name IS NOT NULL
              AND hc.hosting_capacity_mw IS NOT NULL
              AND hc.hosting_capacity_mw > 0
        """)).fetchall()

        utility_iso_map = {}  # utility_id -> iso_id (int)
        for uid, uname, iso_id in utility_rows:
            if iso_id:
                utility_iso_map[uid] = iso_id
                logger.info(f"  Utility {uid} ({uname}) -> iso_id={iso_id}")
            elif uid in ISO_OVERRIDES:
                iso_code = ISO_OVERRIDES[uid]
                iso = db.query(ISO).filter(func.lower(ISO.iso_code) == iso_code.lower()).first()
                if iso:
                    utility_iso_map[uid] = iso.id
                    logger.info(f"  Utility {uid} ({uname}) -> iso_id={iso.id} (override: {iso_code})")
                else:
                    logger.warning(f"  Utility {uid} ({uname}): override ISO '{iso_code}' not found, skipping")
            else:
                logger.warning(f"  Utility {uid} ({uname}): no iso_id, skipping")

        if not utility_iso_map:
            logger.error("No utilities could be mapped to ISOs")
            return

        # Step 2: Get distinct feeders grouped by utility and substation
        logger.info("Querying distinct feeders from hosting_capacity_records...")
        rows = db.execute(text("""
            SELECT feeder_name,
                   substation_name,
                   utility_id,
                   AVG(centroid_lat) as avg_lat,
                   AVG(centroid_lon) as avg_lon,
                   MAX(hosting_capacity_mw) as max_hc_mw,
                   MAX(remaining_capacity_mw) as remaining_mw,
                   MIN(voltage_kv) as voltage_kv,
                   COUNT(*) as record_count
            FROM hosting_capacity_records
            WHERE feeder_name IS NOT NULL
              AND centroid_lat IS NOT NULL
              AND centroid_lon IS NOT NULL
              AND hosting_capacity_mw IS NOT NULL
              AND hosting_capacity_mw > 0
            GROUP BY feeder_name, substation_name, utility_id
        """)).fetchall()
        logger.info(f"Found {len(rows)} distinct (feeder, substation, utility) combos")

        # Step 3: Check existing data to avoid duplicates
        existing_sub_names = set(
            (r[0], r[1]) for r in db.execute(
                text("""SELECT iso_id, substation_name FROM substations""")
            ).fetchall()
        )
        existing_feeders = set(
            r[0] for r in db.execute(
                text("SELECT feeder_id_external FROM feeders WHERE feeder_id_external IS NOT NULL")
            ).fetchall()
        )
        logger.info(f"Existing substations: {len(existing_sub_names)}, feeders: {len(existing_feeders)}")

        # Step 4: Build substations and feeders
        # Group feeders by (utility_id, substation_key) to create substations
        sub_groups = defaultdict(list)  # (utility_id, sub_name) -> list of feeder rows
        skipped_no_iso = 0
        skipped_existing = 0

        for row in rows:
            feeder_name = row[0]
            sub_name = row[1]
            utility_id = row[2]

            if utility_id not in utility_iso_map:
                skipped_no_iso += 1
                continue

            if feeder_name in existing_feeders:
                skipped_existing += 1
                continue

            # Determine substation grouping key
            if sub_name:
                sub_key = sub_name.strip()
            else:
                # No substation name (e.g., DTE): parse prefix from feeder name
                sub_key = f"HC-{_parse_substation_prefix(feeder_name)}"

            sub_groups[(utility_id, sub_key)].append(row)

        logger.info(
            f"Grouping: {len(sub_groups)} substation groups, "
            f"{skipped_no_iso} skipped (no ISO), "
            f"{skipped_existing} skipped (existing)"
        )

        # Step 5: Create Substation and Feeder objects
        created_subs = []
        created_feeders = []
        sub_stats = defaultdict(int)  # utility_id -> count

        for (utility_id, sub_name), feeder_rows in sub_groups.items():
            iso_id = utility_iso_map[utility_id]

            # Check if substation already exists
            if (iso_id, sub_name) in existing_sub_names:
                # Find existing substation
                existing_sub = (
                    db.query(Substation)
                    .filter_by(iso_id=iso_id, substation_name=sub_name)
                    .first()
                )
                sub_id = existing_sub.id if existing_sub else None
            else:
                # Compute centroid from all feeders in this substation
                lats = [float(r[3]) for r in feeder_rows if r[3] is not None]
                lons = [float(r[4]) for r in feeder_rows if r[4] is not None]
                avg_lat = sum(lats) / len(lats) if lats else None
                avg_lon = sum(lons) / len(lons) if lons else None

                sub = Substation(
                    iso_id=iso_id,
                    substation_name=sub_name,
                    bank_name="HC-derived",
                    facility_type="distribution",
                    lat=avg_lat,
                    lon=avg_lon,
                )
                created_subs.append(sub)
                sub_stats[utility_id] += 1
                sub_id = None  # Will be set after flush

            # Create feeders for this substation
            for row in feeder_rows:
                feeder_name = row[0]
                hc_mw = float(row[5]) if row[5] is not None else None
                voltage = float(row[7]) if row[7] is not None else None

                feeder = Feeder(
                    substation_id=sub_id,  # None for new subs, set after flush
                    feeder_id_external=feeder_name,
                    capacity_mw=hc_mw,
                    voltage_kv=voltage,
                )
                # Track which new substation this feeder belongs to
                feeder._pending_sub = sub if sub_id is None else None
                feeder._pending_sub_id = sub_id
                created_feeders.append(feeder)

        logger.info(f"Will create {len(created_subs)} substations:")
        for uid, count in sub_stats.items():
            uname = next((r[1] for r in utility_rows if r[0] == uid), "?")
            logger.info(f"  Utility {uid} ({uname}): {count} substations")
        logger.info(f"Will create {len(created_feeders)} feeders")

        if args.dry_run:
            logger.info("DRY RUN - no changes written")
            return

        if not created_feeders:
            logger.info("No new feeders to create")
            return

        # Step 6: Insert substations first
        logger.info(f"Inserting {len(created_subs)} substations...")
        for i in range(0, len(created_subs), args.batch_size):
            batch = created_subs[i:i + args.batch_size]
            db.add_all(batch)
            db.flush()
            logger.info(f"  Flushed substation batch {i // args.batch_size + 1} ({len(batch)})")

        # Step 7: Link feeders to their substations and insert
        for feeder in created_feeders:
            if feeder._pending_sub is not None:
                feeder.substation_id = feeder._pending_sub.id
            elif feeder._pending_sub_id is not None:
                feeder.substation_id = feeder._pending_sub_id
            # Clean up temp attrs
            del feeder._pending_sub
            del feeder._pending_sub_id

        logger.info(f"Inserting {len(created_feeders)} feeders...")
        for i in range(0, len(created_feeders), args.batch_size):
            batch = created_feeders[i:i + args.batch_size]
            db.add_all(batch)
            db.flush()
            logger.info(f"  Flushed feeder batch {i // args.batch_size + 1} ({len(batch)})")

        db.commit()
        logger.info(f"Committed {len(created_subs)} substations + {len(created_feeders)} feeders")

        # Step 8: Backfill HC records
        logger.info("Building feeder lookup for HC backfill...")
        feeder_lookup = {}
        for f in created_feeders:
            feeder_lookup[f.feeder_id_external] = (f.id, f.substation_id)

        logger.info("Backfilling hosting_capacity_records...")
        updated = 0
        batch_updates = []

        for feeder_name, (feeder_id, substation_id) in feeder_lookup.items():
            batch_updates.append({
                "fname": feeder_name,
                "fid": feeder_id,
                "sid": substation_id,
            })

            if len(batch_updates) >= args.batch_size:
                _execute_backfill(db, batch_updates)
                updated += len(batch_updates)
                logger.info(f"  Backfilled {updated} feeders so far...")
                batch_updates = []

        if batch_updates:
            _execute_backfill(db, batch_updates)
            updated += len(batch_updates)

        db.commit()
        logger.info(f"Backfilled {updated} feeders across hosting_capacity_records")

        # Summary
        total_hc_linked = db.execute(
            text("SELECT COUNT(*) FROM hosting_capacity_records WHERE feeder_id IS NOT NULL")
        ).scalar()
        logger.info(f"Total HC records now linked to feeders: {total_hc_linked}")

    except Exception as e:
        db.rollback()
        logger.error(f"Failed: {e}", exc_info=True)
        sys.exit(1)
    finally:
        db.close()


def _execute_backfill(db, batch_updates):
    """Update HC records in batch."""
    from sqlalchemy import text
    for item in batch_updates:
        db.execute(
            text("""
                UPDATE hosting_capacity_records
                SET feeder_id = :fid, substation_id = :sid
                WHERE feeder_name = :fname AND feeder_id IS NULL
            """),
            item,
        )


if __name__ == "__main__":
    main()
