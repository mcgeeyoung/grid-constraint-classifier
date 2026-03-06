"""Backfill missing zone coordinates using prefix mapping + Nominatim geocoding.

Usage:
    python -m cli.backfill_zone_coords --iso spp [--dry-run] [--limit 50]
"""

import argparse
import json
import logging
import random
import re
import time
from pathlib import Path

from app.database import SessionLocal
from app.models.iso import ISO
from app.models.zone import Zone
from scraping.geocoder import geocode_single

import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# SPP settlement location prefix → parent zone code mapping
# Built from analysis of 1327 SPP settlement location naming patterns
SPP_PREFIX_MAP = {
    # Direct parent zone prefixes
    "SPS": "SPS",
    "OKGE": "OKGE",
    "WFEC": "WFEC",
    "KCPL": "KCPL",
    "GRDA": "GRDA",
    "NPPD": "NPPD",
    "OPPD": "OPPD",
    "WAUE": "WAUE",
    "AEPW": "AEPW",
    # Utility abbreviations → nearest parent zone
    "CSWS": "SPS",       # Central and South West Services (Xcel/SPS area)
    "KMEA": "KCPL",      # Kansas Municipal Energy Agency
    "SECI": "SPS",       # Sunflower Electric (western Kansas)
    "EDE": "AEPW",       # Empire District Electric (SW Missouri/NE Oklahoma)
    "WR": "KCPL",        # Westar Energy (Kansas)
    "LES": "NPPD",       # Lincoln Electric System (Nebraska)
    "OMPA": "OKGE",      # Oklahoma Municipal Power Authority
    "SPRM": "AEPW",      # City Utilities of Springfield
    "AECC": "AEPW",      # Arkansas Electric Cooperative Corp
    "BEPM": "WAUE",      # Basin Electric Power (Dakotas/Montana)
    "MKEC": "KCPL",      # Mid-Kansas Electric Company
    "PSLO": "KCPL",      # PowerSouth (Kansas area)
    "PSGO": "KCPL",      # PowerSouth (Kansas area)
    "FREM": "NPPD",      # Fremont (Nebraska)
    "SARPY": "OPPD",     # Sarpy County (Omaha area)
    "INDNSUB": "NPPD",   # Independence (Nebraska area)
    "SALINA": "KCPL",    # Salina, Kansas
    "KCPLHUB": "KCPL",   # KCPL Hub
    "UCUHUB": "KCPL",    # UCU Hub
    "MPSLAKE": "AEPW",   # MPS Lake
    "PENSACOLA": "GRDA", # Pensacola Dam (Grand River area, OK)
    # Wind farm / generator prefixes
    "CANADIAN": "OKGE",  # Canadian Hills wind farm, OK
    "BUFFALO": "SPS",    # Buffalo Dunes, western Kansas
    "BLUECANYON": "OKGE", # Blue Canyon wind farm, OK
    "CIMARRON": "SPS",   # Cimarron area
    "REDBUD": "OKGE",    # Redbud power plant, OK
    "SOONER": "OKGE",    # Sooner plant, OK
    # Generic fallbacks
    "AEPM": "SPS",       # AEP Market (SPS territory)
    "AEC": "AEPW",       # AEP area
    "AECI": "AEPW",      # Associated Electric Cooperative
    "ALTW": "WAUE",      # Alliant West
    "AMRN": "AEPW",      # Ameren
    "BBA": "AEPW",       # Board of Public Utilities area
    "BCA": "KCPL",       # Burns & McDonnell area
}

# Parent zone coordinates (from spp.yaml)
PARENT_ZONE_COORDS = {
    "SPS":  (34.75, -102.00),
    "WFEC": (35.20, -97.50),
    "OKGE": (35.47, -97.52),
    "KCPL": (39.10, -94.57),
    "GRDA": (36.30, -95.30),
    "AEPW": (35.50, -95.00),
    "NPPD": (41.00, -100.00),
    "OPPD": (41.26, -95.94),
    "WAUE": (46.00, -100.00),
}

# States for each parent zone (for geocoding context)
PARENT_ZONE_STATES = {
    "SPS":  "Texas",
    "WFEC": "Oklahoma",
    "OKGE": "Oklahoma",
    "KCPL": "Kansas",
    "GRDA": "Oklahoma",
    "AEPW": "Oklahoma",
    "NPPD": "Nebraska",
    "OPPD": "Nebraska",
    "WAUE": "South Dakota",
}


def find_parent_zone(zone_code: str) -> str | None:
    """Map a settlement location code to its parent zone via prefix matching."""
    # Try exact match first
    if zone_code in SPP_PREFIX_MAP:
        return SPP_PREFIX_MAP[zone_code]

    # Try progressively shorter prefixes
    for length in range(min(len(zone_code), 10), 2, -1):
        prefix = zone_code[:length]
        if prefix in SPP_PREFIX_MAP:
            return SPP_PREFIX_MAP[prefix]

    # Try first part before underscore
    parts = zone_code.split("_")
    if parts[0] in SPP_PREFIX_MAP:
        return SPP_PREFIX_MAP[parts[0]]

    return None


def extract_geographic_name(zone_code: str, parent_prefix: str | None = None) -> str | None:
    """Extract the geographic/place name from a settlement location code.

    Returns a cleaned name suitable for geocoding, or None if no geographic
    part can be extracted.
    """
    name = zone_code

    # Remove known utility prefix
    if parent_prefix:
        for pfx in SPP_PREFIX_MAP:
            if name.startswith(pfx) and len(name) > len(pfx):
                suffix = name[len(pfx):]
                # Remove separator
                suffix = suffix.lstrip("_.")
                if suffix:
                    name = suffix
                    break

    # Remove trailing numbers and separators
    name = re.sub(r"[\d_]+$", "", name)
    # Remove leading numbers
    name = re.sub(r"^\d+[_\s]*", "", name)
    # Replace underscores with spaces
    name = name.replace("_", " ").strip()
    # Remove common non-geographic suffixes
    for suffix in ["HUB", "DDR", "GEN", "LD", "WIND", "SOLAR", "SUB"]:
        if name.endswith(f" {suffix}"):
            name = name[: -(len(suffix) + 1)].strip()

    # Must be at least 3 chars and contain letters
    if len(name) < 3 or not re.search(r"[A-Za-z]{3,}", name):
        return None

    return name


def backfill_iso_zones(
    iso_code: str,
    dry_run: bool = False,
    limit: int | None = None,
):
    """Backfill missing zone coordinates for an ISO."""
    db = SessionLocal()
    cache_path = Path(f"data/{iso_code}/zone_coord_cache.json")

    try:
        iso = db.query(ISO).filter(ISO.iso_code == iso_code).first()
        if not iso:
            logger.error(f"ISO '{iso_code}' not found")
            return

        # Get zones without coordinates
        query = db.query(Zone).filter(
            Zone.iso_id == iso.id,
            Zone.centroid_lat.is_(None),
        )
        if limit:
            query = query.limit(limit)
        zones = query.all()

        logger.info(f"Found {len(zones)} zones without coordinates for {iso_code}")
        if not zones:
            return

        # Load cache
        cache = {}
        if cache_path.exists():
            with open(cache_path) as f:
                cache = json.load(f)
            logger.info(f"Loaded {len(cache)} cached coordinates")

        # Build geocoding queue
        to_geocode = []
        prefix_mapped = 0
        cached = 0

        for zone in zones:
            code = zone.zone_code
            if code in cache:
                cached += 1
                continue

            parent = find_parent_zone(code)
            if parent:
                prefix_mapped += 1

            geo_name = extract_geographic_name(code, parent)
            to_geocode.append((zone, parent, geo_name))

        logger.info(
            f"Queue: {len(to_geocode)} to geocode, {cached} cached, "
            f"{prefix_mapped} mapped to parent zones"
        )

        if not to_geocode and not cached:
            return

        # Geocode new entries
        session = requests.Session()
        nominatim_hits = 0
        centroid_fallbacks = 0

        for i, (zone, parent, geo_name) in enumerate(to_geocode):
            code = zone.zone_code
            coords = None

            # Try Nominatim geocoding if we have a geographic name
            if geo_name:
                state = PARENT_ZONE_STATES.get(parent, "")
                query_str = f"{geo_name}, {state}, USA" if state else f"{geo_name}, USA"
                coords = geocode_single(session, query_str)
                if coords:
                    cache[code] = {
                        "lat": coords[0],
                        "lon": coords[1],
                        "source": "nominatim",
                        "parent_zone": parent,
                    }
                    nominatim_hits += 1

            # Fall back to parent zone centroid with jitter
            if not coords:
                if parent and parent in PARENT_ZONE_COORDS:
                    base_lat, base_lon = PARENT_ZONE_COORDS[parent]
                else:
                    # Default to center of SPP footprint
                    base_lat, base_lon = 37.5, -98.0

                cache[code] = {
                    "lat": base_lat + random.uniform(-0.8, 0.8),
                    "lon": base_lon + random.uniform(-0.8, 0.8),
                    "source": "parent_centroid",
                    "parent_zone": parent,
                }
                centroid_fallbacks += 1

            if (i + 1) % 50 == 0:
                logger.info(
                    f"  Progress: {i + 1}/{len(to_geocode)} "
                    f"({nominatim_hits} geocoded, {centroid_fallbacks} fallback)"
                )

            # Rate limit for Nominatim (only when we made a request)
            if geo_name:
                time.sleep(1.05)

        logger.info(
            f"Geocoding complete: {nominatim_hits} via Nominatim, "
            f"{centroid_fallbacks} via parent centroid"
        )

        # Save cache
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        with open(cache_path, "w") as f:
            json.dump(cache, f, indent=2)
        logger.info(f"Saved {len(cache)} coordinates to {cache_path}")

        # Apply coordinates to database
        if dry_run:
            logger.info("Dry run, skipping database updates")
            return

        updated = 0
        for zone in zones:
            if zone.zone_code in cache:
                entry = cache[zone.zone_code]
                zone.centroid_lat = entry["lat"]
                zone.centroid_lon = entry["lon"]
                updated += 1

        db.commit()
        logger.info(f"Updated {updated} zone coordinates in database")

    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description="Backfill missing zone coordinates")
    parser.add_argument("--iso", required=True, help="ISO code (e.g., spp)")
    parser.add_argument("--dry-run", action="store_true", help="Don't update database")
    parser.add_argument("--limit", type=int, help="Limit number of zones to process")
    parser.add_argument(
        "--skip-geocoding",
        action="store_true",
        help="Skip Nominatim, only use prefix mapping + centroid fallback",
    )
    args = parser.parse_args()

    if args.skip_geocoding:
        # Fast path: just apply prefix mapping without Nominatim
        db = SessionLocal()
        try:
            iso = db.query(ISO).filter(ISO.iso_code == args.iso).first()
            if not iso:
                logger.error(f"ISO '{args.iso}' not found")
                return

            zones = db.query(Zone).filter(
                Zone.iso_id == iso.id,
                Zone.centroid_lat.is_(None),
            ).all()

            logger.info(f"Fast backfill: {len(zones)} zones without coords")
            updated = 0
            for zone in zones:
                parent = find_parent_zone(zone.zone_code)
                if parent and parent in PARENT_ZONE_COORDS:
                    base_lat, base_lon = PARENT_ZONE_COORDS[parent]
                else:
                    base_lat, base_lon = 37.5, -98.0

                zone.centroid_lat = base_lat + random.uniform(-0.8, 0.8)
                zone.centroid_lon = base_lon + random.uniform(-0.8, 0.8)
                updated += 1

            if not args.dry_run:
                db.commit()
                logger.info(f"Updated {updated} zones with parent centroid coordinates")
            else:
                logger.info(f"Dry run: would update {updated} zones")
        finally:
            db.close()
    else:
        backfill_iso_zones(args.iso, dry_run=args.dry_run, limit=args.limit)


if __name__ == "__main__":
    main()
