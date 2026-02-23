"""
ISO-specific zone boundary downloaders.

For ISOs that provide their own GIS zone polygons (not via HIFLD).
Currently supports NYISO via an ArcGIS Online FeatureServer.
"""

import json
import logging
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

# NYISO Load Zone polygons (Zones A-K) hosted on ArcGIS Online
NYISO_LOAD_ZONES_URL = (
    "https://services3.arcgis.com/IjH5oxISveik310X/arcgis/rest/services/"
    "NYISO_Load_Zones/FeatureServer/0/query"
)

# Map single-letter zone codes to the gridstatus abbreviated names
# used in classification data (these come from NYISO's own LMP feed)
NYISO_LETTER_TO_GRIDSTATUS = {
    "A": "WEST",
    "B": "GENESE",
    "C": "CENTRL",
    "D": "NORTH",
    "E": "MHK VL",
    "F": "CAPITL",
    "G": "HUD VL",
    "H": "MILLWD",
    "I": "DUNWOD",
    "J": "N.Y.C.",
    "K": "LONGIL",
}


def download_nyiso_zone_boundaries(
    cache_path: Path,
    force: bool = False,
) -> dict:
    """
    Download NYISO load zone boundary polygons from ArcGIS Online.

    Returns GeoJSON FeatureCollection with iso_zone property set to the
    gridstatus abbreviated zone name (e.g. LONGIL, N.Y.C.) so it matches
    the classification data.
    """
    if cache_path.exists() and not force:
        logger.info(f"Loading cached NYISO zone boundaries from {cache_path}")
        with open(cache_path) as f:
            return json.load(f)

    logger.info("Downloading NYISO load zone boundaries...")

    params = {
        "where": "1=1",
        "outFields": "*",
        "f": "geojson",
        "outSR": 4326,
    }

    try:
        resp = requests.get(NYISO_LOAD_ZONES_URL, params=params, timeout=120)
        resp.raise_for_status()
        geojson = resp.json()

        # Tag each feature with iso_zone using gridstatus zone names
        matched = 0
        for feat in geojson.get("features", []):
            props = feat.get("properties", {})
            letter = (props.get("Zone_Name") or "").strip().upper()
            gs_name = NYISO_LETTER_TO_GRIDSTATUS.get(letter, "")
            feat["properties"]["iso_zone"] = gs_name
            if gs_name:
                matched += 1

        cache_path.parent.mkdir(parents=True, exist_ok=True)
        with open(cache_path, "w") as f:
            json.dump(geojson, f)

        total = len(geojson.get("features", []))
        logger.info(
            f"Downloaded {total} NYISO zone features, "
            f"matched {matched} to zone codes"
        )
        return geojson

    except Exception as e:
        logger.warning(f"Failed to download NYISO zone boundaries: {e}")
        return {"type": "FeatureCollection", "features": []}
