"""
Load PJM zone boundaries from HIFLD Electric Retail Service Territories.

Maps HIFLD utility names to PJM zone codes and writes boundary_geojson
to the Zone records in the database.
"""

import logging
import sys
from pathlib import Path
from typing import Optional

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

# HIFLD utility name(s) → PJM zone code
# Some zones need multiple utilities merged
ZONE_UTILITY_MAP = {
    "DOM": ["VIRGINIA ELECTRIC & POWER CO"],
    "AEP": ["Appalachian Power Co", "Ohio Power Co", "Indiana Michigan Power Co", "Kentucky Power Co"],
    "APS": ["WEST PENN POWER COMPANY", "Monongahela Power Co", "THE POTOMAC EDISON COMPANY"],
    "ATSI": ["Ohio Edison Co", "CLEVELAND ELECTRIC ILLUM CO", "THE TOLEDO EDISON CO"],
    "BGE": ["Baltimore Gas & Electric Co"],
    "COMED": ["Commonwealth Edison Co"],
    "DAY": ["Dayton Power & Light Co"],
    "DEOK": ["Duke Energy Ohio Inc", "DUKE ENERGY KENTUCKY"],
    "DPL": ["DELMARVA POWER"],
    "DUQ": ["Duquesne Light Co"],
    "EKPC": ["EAST KENTUCKY POWER COOP, INC"],
    "JCPL": ["Jersey Central Power & Lt Co"],
    "METED": ["Metropolitan Edison Co"],
    "PECO": ["PECO Energy Co"],
    "PENELEC": ["Pennsylvania Electric Co"],
    "PEPCO": ["Potomac Electric Power Co"],
    "PPL": ["PPL Electric Utilities Corp"],
    "PSEG": ["Public Service Elec & Gas Co"],
    "RECO": ["Rockland Electric Co"],
    "AECO": ["Atlantic City Electric Co"],
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
    log.info("Loading PJM zone boundaries from HIFLD")

    db = SessionLocal()
    iso = db.query(ISO).filter(ISO.iso_code == "pjm").first()
    if not iso:
        log.error("PJM ISO not found in database")
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

        log.info(f"  {zone_code}: fetching {len(utility_names)} utilities...")
        geoms = []
        for name in utility_names:
            geom = fetch_utility_boundary(name)
            if geom:
                geoms.append(geom)
                log.info(f"    {name}: OK")
            else:
                log.warning(f"    {name}: NOT FOUND")

        if geoms:
            merged = unary_union(geoms) if len(geoms) > 1 else geoms[0]
            zone.boundary_geojson = mapping(merged)
            updated += 1
            log.info(f"    {zone_code}: boundary set ({merged.geom_type})")
        else:
            failed.append(zone_code)
            log.warning(f"    {zone_code}: NO GEOMETRIES FOUND")

    db.commit()
    log.info(f"\nDone: {updated} zone boundaries written")
    if failed:
        log.warning(f"Failed zones: {failed}")

    # Report coverage
    total = len(zones)
    with_boundary = sum(1 for z in zones if z.boundary_geojson is not None)
    log.info(f"PJM boundary coverage: {with_boundary}/{total} zones")

    db.close()


if __name__ == "__main__":
    main()
