"""Ingest PG&E GRIP substation load profiles into the database."""

import logging
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.database import SessionLocal
from app.models import Substation, SubstationLoadProfile
from scraping.grip_fetcher import fetch_substation_load_profiles

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
logger = logging.getLogger(__name__)

CACHE_PATH = Path("data/caiso/grip_load_profiles.csv")


def main(force: bool = False):
    df = fetch_substation_load_profiles(CACHE_PATH, force=force)
    if df.empty:
        logger.warning("No load profile data to ingest")
        return

    db = SessionLocal()
    try:
        # Build substation name -> list of IDs (multiple banks per name)
        subs = db.query(Substation.id, Substation.substation_name).all()
        name_to_ids: dict[str, list[int]] = {}
        for sub_id, name in subs:
            key = name.strip().upper()
            name_to_ids.setdefault(key, []).append(sub_id)

        matched = 0
        unmatched_names = set()
        rows = []

        for _, row in df.iterrows():
            subname = row["subname"]
            sub_ids = name_to_ids.get(subname)
            if not sub_ids:
                unmatched_names.add(subname)
                continue

            for sub_id in sub_ids:
                matched += 1
                rows.append({
                    "substation_id": sub_id,
                    "month": int(row["month"]),
                    "hour": int(row["hour"]),
                    "load_low_kw": float(row["low"]),
                    "load_high_kw": float(row["high"]),
                })

        logger.info(
            f"Matched {matched} records ({len(rows)} rows) to {len(name_to_ids)} DB substations. "
            f"{len(unmatched_names)} substation names not found in DB."
        )

        if not rows:
            logger.warning("No rows to insert")
            return

        # Upsert in batches
        batch_size = 1000
        total_upserted = 0
        for i in range(0, len(rows), batch_size):
            batch = rows[i:i + batch_size]
            stmt = pg_insert(SubstationLoadProfile).values(batch)
            stmt = stmt.on_conflict_do_update(
                constraint="uq_sub_load_profile",
                set_={
                    "load_low_kw": stmt.excluded.load_low_kw,
                    "load_high_kw": stmt.excluded.load_high_kw,
                },
            )
            db.execute(stmt)
            total_upserted += len(batch)

        db.commit()
        logger.info(f"Upserted {total_upserted} load profile records")

        if unmatched_names:
            logger.info(f"Sample unmatched: {sorted(unmatched_names)[:10]}")

    finally:
        db.close()


if __name__ == "__main__":
    force = "--force" in sys.argv
    main(force=force)
