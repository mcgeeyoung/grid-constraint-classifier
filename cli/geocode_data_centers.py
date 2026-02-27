"""Geocode data centers using county+state via Nominatim.

Geocodes 187 unique county+state combos, then updates all 1,909 DC records.
Caches results to avoid re-geocoding on repeat runs.
Rate limit: 1 req/sec per Nominatim terms of use.
"""

import json
import logging
import sys
import time
from pathlib import Path

import requests
from sqlalchemy import update

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import SessionLocal
from app.models import DataCenter

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

CACHE_PATH = Path(__file__).resolve().parent.parent / "data" / "dc_geocode_cache.json"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"


def geocode_county(session, county, state):
    """Geocode a county+state pair via Nominatim. Returns (lat, lon) or None."""
    # Clean up county name (remove "County" suffix if present for cleaner query)
    query = f"{county}, {state}, USA"
    try:
        resp = session.get(
            NOMINATIM_URL,
            params={"q": query, "format": "json", "limit": 1, "countrycodes": "us"},
            headers={"User-Agent": "grid-constraint-classifier/2.0 (dc-geocoding)"},
            timeout=10,
        )
        resp.raise_for_status()
        results = resp.json()
        if results:
            return (float(results[0]["lat"]), float(results[0]["lon"]))
    except Exception as e:
        logger.warning(f"Geocode failed for '{query}': {e}")
    return None


def main():
    # Load cache
    cache: dict[str, list[float]] = {}
    if CACHE_PATH.exists():
        with open(CACHE_PATH) as f:
            cache = json.load(f)
        logger.info(f"Loaded {len(cache)} cached geocodes")

    db = SessionLocal()

    # Get unique county+state combos
    from sqlalchemy import func, distinct
    combos = (
        db.query(DataCenter.county, DataCenter.state_code)
        .group_by(DataCenter.county, DataCenter.state_code)
        .all()
    )
    logger.info(f"Found {len(combos)} unique county+state combos")

    # Geocode missing combos
    to_geocode = [(c, s) for c, s in combos if f"{c}|{s}" not in cache]
    logger.info(f"{len(cache)} cached, {len(to_geocode)} to geocode")

    if to_geocode:
        session = requests.Session()
        success = 0
        failed = 0

        for i, (county, state) in enumerate(to_geocode):
            key = f"{county}|{state}"
            result = geocode_county(session, county, state)
            if result:
                cache[key] = [result[0], result[1]]
                success += 1
            else:
                failed += 1
                logger.warning(f"  No result for: {county}, {state}")

            if (i + 1) % 20 == 0:
                logger.info(f"  Geocoded {i + 1}/{len(to_geocode)}...")

            time.sleep(1.05)  # Respect Nominatim rate limit

        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(CACHE_PATH, "w") as f:
            json.dump(cache, f, indent=2)
        logger.info(f"Geocoding done: {success} success, {failed} failed. Cache saved.")

    # Update DB
    updated = 0
    for county, state in combos:
        key = f"{county}|{state}"
        if key not in cache:
            continue
        lat, lon = cache[key]
        count = (
            db.query(DataCenter)
            .filter(DataCenter.county == county, DataCenter.state_code == state, DataCenter.lat.is_(None))
            .update({DataCenter.lat: lat, DataCenter.lon: lon})
        )
        updated += count

    db.commit()
    total_with_coords = db.query(DataCenter).filter(DataCenter.lat.isnot(None)).count()
    total = db.query(DataCenter).count()
    logger.info(f"Updated {updated} records. {total_with_coords}/{total} now have coordinates.")
    db.close()


if __name__ == "__main__":
    main()
