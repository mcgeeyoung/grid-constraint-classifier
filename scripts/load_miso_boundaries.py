"""
Load MISO zone boundaries from HIFLD Electric Retail Service Territories.

Maps HIFLD utility names to MISO zone codes and writes boundary_geojson
to the Zone records in the database.

Of 43 MISO zones, 29 already have boundaries. Of the 14 remaining:
  - 5 have direct HIFLD matches (loaded by this script)
  - 9 are generation cooperatives or small municipals with no HIFLD polygon

Unmatchable zones (no HIFLD service territory):
  BLEC  Blue Star Energy          (small IL marketer)
  BREC  Big Rivers Electric       (KY generation coop)
  CILC  Central IL Light Co       (merged into Ameren Illinois, overlaps AMIL)
  DPC   Dairyland Power           (WI generation coop)
  GRE   Great River Energy        (MN generation coop)
  LEPA  Louisiana Energy & Power  (small LA municipal authority)
  MPW   Muscatine Power & Water   (small IA municipal)
  SCEG  South Central Electric    (SD, not in HIFLD)
  SME   South Mississippi Elec    (MS generation coop)

Usage:
    python scripts/load_miso_boundaries.py
    python scripts/load_miso_boundaries.py --dry-run
"""

import argparse
import logging
import sys
from pathlib import Path

import requests
from shapely.geometry import shape, mapping
from shapely.ops import unary_union

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import SessionLocal
from app.models import ISO, Zone

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger(__name__)

HIFLD_URL = (
    "https://services3.arcgis.com/OYP7N6mAJJCyH6hd/arcgis/rest/services/"
    "Electric_Retail_Service_Territories_HIFLD/FeatureServer/0/query"
)

# HIFLD utility name(s) -> MISO zone code
ZONE_UTILITY_MAP = {
    "AMIL": ["AMEREN ILLINOIS COMPANY"],
    "HE": ["ALLETE, INC."],
    "MHEB": ["MONTANA-DAKOTA UTILITIES CO"],
    "MIUP": ["UPPER PENINSULA POWER COMPANY"],
    "OVEC": ["OHIO VALLEY ELECTRIC CORP"],
}


def fetch_utility_boundary(utility_name):
    """Fetch a utility's service territory polygon from HIFLD."""
    params = {
        "where": f"NAME = '{utility_name}'",
        "outFields": "NAME",
        "f": "geojson",
        "outSR": 4326,
    }
    try:
        resp = requests.get(HIFLD_URL, params=params, timeout=60)
        resp.raise_for_status()
        features = resp.json().get("features", [])
        if not features:
            return None
        if len(features) == 1:
            return shape(features[0]["geometry"])
        return unary_union([shape(f["geometry"]) for f in features])
    except Exception as e:
        log.warning(f"  Failed for '{utility_name}': {e}")
        return None


def main():
    parser = argparse.ArgumentParser(
        description="Load MISO zone boundaries from HIFLD",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch and report without writing to DB",
    )
    args = parser.parse_args()

    log.info("Loading MISO zone boundaries from HIFLD")

    db = SessionLocal()
    iso = db.query(ISO).filter(ISO.iso_code == "miso").first()
    if not iso:
        log.error("MISO ISO not found in database")
        return

    zones = db.query(Zone).filter(Zone.iso_id == iso.id).all()
    zone_lookup = {z.zone_code: z for z in zones}

    updated = 0
    failed = []

    for zone_code, utility_names in ZONE_UTILITY_MAP.items():
        zone = zone_lookup.get(zone_code)
        if not zone:
            log.warning(f"  {zone_code}: not found in DB, skipping")
            continue

        if zone.boundary_geojson is not None:
            log.info(f"  {zone_code}: already has boundary, skipping")
            continue

        log.info(f"  {zone_code}: fetching {len(utility_names)} utilities...")
        geoms = []
        for name in utility_names:
            geom = fetch_utility_boundary(name)
            if geom:
                geoms.append(geom)
                log.info(f"    {name}: OK ({geom.geom_type})")
            else:
                log.warning(f"    {name}: NOT FOUND")

        if geoms:
            merged = unary_union(geoms) if len(geoms) > 1 else geoms[0]
            if args.dry_run:
                log.info(f"    {zone_code}: would set boundary ({merged.geom_type})")
            else:
                zone.boundary_geojson = mapping(merged)
                updated += 1
                log.info(f"    {zone_code}: boundary set ({merged.geom_type})")
        else:
            failed.append(zone_code)
            log.warning(f"    {zone_code}: NO GEOMETRIES FOUND")

    if not args.dry_run:
        db.commit()

        # Sync boundary_geojson -> boundary_geom (PostGIS)
        from sqlalchemy import text
        with db.bind.connect() as conn:
            r = conn.execute(text("""
                UPDATE zones
                SET boundary_geom = ST_SetSRID(
                    ST_GeomFromGeoJSON(boundary_geojson::text), 4326
                )
                WHERE boundary_geojson IS NOT NULL AND boundary_geom IS NULL
            """))
            conn.commit()
            log.info(f"Synced {r.rowcount} boundary_geom columns")

    log.info(f"\nDone: {updated} zone boundaries written")
    if failed:
        log.warning(f"Failed zones: {failed}")

    # Report coverage
    total = len(zones)
    with_boundary = sum(1 for z in zones if z.boundary_geojson is not None)
    log.info(f"MISO boundary coverage: {with_boundary}/{total} zones")

    db.close()


if __name__ == "__main__":
    main()
