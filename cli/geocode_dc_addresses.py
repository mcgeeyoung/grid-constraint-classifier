"""Geocode data centers using full street addresses via Nominatim.

Reads addresses from dc_combined.json source files, geocodes each facility,
and updates lat/lon/geom in the database. Caches results to avoid redundant lookups.
Rate limit: 1 req/sec per Nominatim terms of use.
"""

import json
import logging
import sys
import time
from pathlib import Path

import requests
from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import SessionLocal
from app.models import DataCenter

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
CACHE_PATH = DATA_DIR / "dc_address_geocode_cache.json"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"


def geocode_address(session, address: str, city: str, state: str, zipcode: str):
    """Geocode a full address via Nominatim. Returns (lat, lon) or None."""
    parts = [p for p in [address, city, state, zipcode] if p]
    query = ", ".join(parts) + ", USA"
    try:
        resp = session.get(
            NOMINATIM_URL,
            params={"q": query, "format": "json", "limit": 1, "countrycodes": "us"},
            headers={"User-Agent": "grid-constraint-classifier/2.0 (dc-address-geocoding)"},
            timeout=10,
        )
        resp.raise_for_status()
        results = resp.json()
        if results:
            return (float(results[0]["lat"]), float(results[0]["lon"]))
    except Exception as e:
        logger.warning(f"Geocode failed for '{query}': {e}")
    return None


def load_source_records() -> dict[str, dict]:
    """Load all dc_combined.json source files and index by slug."""
    records = {}
    paths = list(DATA_DIR.glob("*/data_centers/dc_combined.json"))
    paths.append(DATA_DIR / "data_centers" / "dc_combined.json")
    for p in paths:
        if not p.exists():
            continue
        with open(p) as f:
            data = json.load(f)
        for r in data:
            slug = r.get("slug")
            if slug:
                records[slug] = r
    logger.info(f"Loaded {len(records)} source records with addresses")
    return records


def main():
    # Load cache
    cache: dict[str, list[float] | None] = {}
    if CACHE_PATH.exists():
        with open(CACHE_PATH) as f:
            cache = json.load(f)
        logger.info(f"Loaded {len(cache)} cached geocodes")

    # Load source data with addresses
    source = load_source_records()

    db = SessionLocal()
    all_dcs = db.query(DataCenter).all()
    logger.info(f"Found {len(all_dcs)} data centers in DB")

    http = requests.Session()
    geocoded = 0
    skipped = 0
    failed = 0
    updated = 0

    for dc in all_dcs:
        slug = dc.external_slug
        if not slug or slug not in source:
            skipped += 1
            continue

        src = source[slug]
        address = src.get("address", "")
        city = src.get("city", "")
        state = src.get("state_code", "") or dc.state_code or ""
        zipcode = src.get("zip", "")

        if not address:
            skipped += 1
            continue

        cache_key = f"{address}|{city}|{state}|{zipcode}"

        if cache_key not in cache:
            result = geocode_address(http, address, city, state, zipcode)
            cache[cache_key] = list(result) if result else None
            geocoded += 1
            time.sleep(1.05)  # Nominatim rate limit

            if geocoded % 25 == 0:
                logger.info(f"  Geocoded {geocoded}...")
                # Save cache periodically
                with open(CACHE_PATH, "w") as f:
                    json.dump(cache, f, indent=2)

        coords = cache.get(cache_key)
        if coords:
            dc.lat = coords[0]
            dc.lon = coords[1]
            updated += 1
        else:
            failed += 1

    # Update geom from lat/lon
    db.commit()
    db.execute(text("""
        UPDATE data_centers
        SET geom = ST_SetSRID(ST_MakePoint(lon, lat), 4326)
        WHERE lat IS NOT NULL AND lon IS NOT NULL
    """))
    db.commit()

    # Save final cache
    with open(CACHE_PATH, "w") as f:
        json.dump(cache, f, indent=2)

    logger.info(
        f"Done: {updated} updated, {geocoded} newly geocoded, "
        f"{failed} failed, {skipped} skipped (no address/source)"
    )
    db.close()


if __name__ == "__main__":
    main()
