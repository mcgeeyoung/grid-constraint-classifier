"""
Load CAISO Sub-LAP zone boundaries into the database.

Sources:
  - PG&E divisions: data/caiso/division_boundaries.json (19 PG&E division polygons)
  - SCE/SDG&E/VEA: HIFLD Electric Retail Service Territories API

PG&E divisions don't map 1:1 to Sub-LAPs, so some divisions are merged
using shapely unary_union to form the correct SLAP boundary.
"""

import json
import logging
from pathlib import Path
from typing import Optional

import requests
from shapely.geometry import shape, mapping
from shapely.ops import unary_union

# Append project root to path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import SessionLocal
from app.models import ISO, Zone

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "caiso"

# ── PG&E division → Sub-LAP mapping ──
# 11 clear 1:1 matches, 4 SLAPs formed by merging multiple divisions
DIVISION_TO_SLAP = {
    # 1:1 matches
    "Central Coast": "SLAP_PGCC-APND",
    "East Bay": "SLAP_PGEB-APND",
    "Fresno": "SLAP_PGF1-APND",
    "Humboldt": "SLAP_PGHB-APND",
    "Kern": "SLAP_PGKN-APND",
    "Los Padres": "SLAP_PGLP-APND",
    "North Bay": "SLAP_PGNB-APND",
    "Peninsula": "SLAP_PGP2-APND",
    "San Francisco": "SLAP_PGSF-APND",
    "Sierra": "SLAP_PGSI-APND",
    "Stockton": "SLAP_PGST-APND",
    # Multi-division merges
    "Sonoma": "SLAP_PGNC-APND",          # North Coast
    "Sacramento": "SLAP_PGNP-APND",      # North Path
    "North Valley": "SLAP_PGNP-APND",    # North Path (merged with Sacramento)
    "San Jose": "SLAP_PGSB-APND",        # South Bay
    "De Anza": "SLAP_PGSB-APND",         # South Bay (merged with San Jose)
    "Mission": "SLAP_PGSB-APND",         # South Bay (merged with San Jose + De Anza)
    "Diablo": "SLAP_PGEB-APND",          # East Bay (merged with East Bay)
    "Yosemite": "SLAP_PGF1-APND",        # Fresno (merged with Fresno)
}
# Note: SLAP_PGFG-APND (Geysers) has no matching division - it's a small
# geothermal generation area, not a service territory division

# ── HIFLD service territory lookup for SCE, SDG&E, VEA ──
HIFLD_TERRITORY_URL = (
    "https://services3.arcgis.com/OYP7N6mAJJCyH6hd/arcgis/rest/services/"
    "Electric_Retail_Service_Territories_HIFLD/FeatureServer/0/query"
)

# HIFLD utility names → SLAP zone codes
# SCE has 6 sub-zones but HIFLD only has the full territory.
# We assign the full territory to the largest sub-zone (Core/LA Basin).
HIFLD_UTILITIES = {
    "Southern California Edison Co": "SLAP_SCEC-APND",  # SCE Core (largest)
    "San Diego Gas & Electric Co": "SLAP_SDG1-APND",
    "Valley Electric Assn, Inc": "SLAP_VEA-APND",
}


def load_pge_divisions() -> dict:
    """Load PG&E division boundaries and merge into SLAP zones."""
    path = DATA_DIR / "division_boundaries.json"
    if not path.exists():
        log.error(f"PG&E division boundaries not found at {path}")
        return {}

    with open(path) as f:
        data = json.load(f)

    # Group geometries by target SLAP zone
    slap_geometries: dict[str, list] = {}
    for feat in data.get("features", []):
        div_name = feat["properties"]["division"]
        slap_code = DIVISION_TO_SLAP.get(div_name)
        if not slap_code:
            log.warning(f"  No SLAP mapping for division: {div_name}")
            continue
        geom = shape(feat["geometry"])
        slap_geometries.setdefault(slap_code, []).append(geom)

    # Merge multi-division geometries
    result = {}
    for slap_code, geoms in slap_geometries.items():
        if len(geoms) == 1:
            merged = geoms[0]
        else:
            merged = unary_union(geoms)
        result[slap_code] = mapping(merged)
        div_count = len(geoms)
        log.info(f"  {slap_code}: {div_count} division(s) merged")

    return result


def fetch_hifld_utility_boundary(utility_name: str) -> Optional[dict]:
    """Fetch a single utility's service territory from HIFLD."""
    params = {
        "where": f"NAME = '{utility_name}'",
        "outFields": "NAME,STATE",
        "f": "geojson",
        "outSR": 4326,
    }

    try:
        resp = requests.get(HIFLD_TERRITORY_URL, params=params, timeout=60)
        resp.raise_for_status()
        geojson = resp.json()
        features = geojson.get("features", [])

        if not features:
            log.warning(f"  No HIFLD features found for: {utility_name}")
            return None

        # If multiple features, merge them
        if len(features) == 1:
            return features[0]["geometry"]
        else:
            geoms = [shape(f["geometry"]) for f in features]
            merged = unary_union(geoms)
            return mapping(merged)

    except Exception as e:
        log.error(f"  HIFLD fetch failed for {utility_name}: {e}")
        return None


def main():
    log.info("Loading CAISO Sub-LAP zone boundaries")

    # Step 1: PG&E divisions → SLAP zones
    log.info("\n── PG&E Division Boundaries ──")
    pge_boundaries = load_pge_divisions()
    log.info(f"  PG&E: {len(pge_boundaries)} SLAP zones from divisions")

    # Step 2: SCE, SDG&E, VEA from HIFLD
    log.info("\n── HIFLD Utility Boundaries ──")
    hifld_boundaries = {}
    for utility_name, slap_code in HIFLD_UTILITIES.items():
        log.info(f"  Fetching {utility_name} → {slap_code}...")
        geom = fetch_hifld_utility_boundary(utility_name)
        if geom:
            hifld_boundaries[slap_code] = geom
            log.info(f"    OK ({geom['type']})")
        else:
            log.warning(f"    FAILED")

    # Combine all boundaries
    all_boundaries = {**pge_boundaries, **hifld_boundaries}
    log.info(f"\nTotal boundaries: {len(all_boundaries)} / 23 zones")

    # Step 3: Write to database
    log.info("\n── Writing to Database ──")
    db = SessionLocal()
    try:
        iso = db.query(ISO).filter(ISO.iso_code == "caiso").first()
        if not iso:
            log.error("CAISO ISO not found in database!")
            return

        zones = db.query(Zone).filter(Zone.iso_id == iso.id).all()
        zone_lookup = {z.zone_code: z for z in zones}

        updated = 0
        for slap_code, geometry in all_boundaries.items():
            zone = zone_lookup.get(slap_code)
            if not zone:
                log.warning(f"  Zone {slap_code} not found in DB, skipping")
                continue
            zone.boundary_geojson = geometry
            updated += 1
            log.info(f"  {slap_code}: boundary set ({geometry['type']})")

        db.commit()
        log.info(f"\nDone: {updated} zone boundaries written to DB")

        # Report missing
        missing = [z.zone_code for z in zones if z.boundary_geojson is None]
        if missing:
            log.info(f"Still missing boundaries: {missing}")

    except Exception as e:
        log.error(f"Database error: {e}")
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    main()
