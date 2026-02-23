"""
HIFLD (Homeland Infrastructure Foundation-Level Data) utilities.

Downloads transmission lines and utility service territory boundaries
from HIFLD ArcGIS FeatureServers. Works nationwide across all ISOs.
"""

import json
import logging
from pathlib import Path
from typing import Optional

import requests

logger = logging.getLogger(__name__)

HIFLD_TX_URL = (
    "https://services1.arcgis.com/Hp6G80Pky0om7QvQ/arcgis/rest/services/"
    "Electric_Power_Transmission_Lines/FeatureServer/0"
)

HIFLD_TERRITORY_URL = (
    "https://services3.arcgis.com/OYP7N6mAJJCyH6hd/arcgis/rest/services/"
    "Electric_Retail_Service_Territories_HIFLD/FeatureServer/0"
)


def download_transmission_lines(
    cache_path: Path,
    min_voltage: int = 230,
    force: bool = False,
) -> dict:
    """
    Download transmission lines (230kV+ by default) from HIFLD.

    Returns GeoJSON FeatureCollection. Not rate-limited.
    """
    if cache_path.exists() and not force:
        logger.info(f"Loading cached transmission lines from {cache_path}")
        with open(cache_path) as f:
            return json.load(f)

    url = f"{HIFLD_TX_URL}/query"
    params = {
        "where": f"VOLTAGE >= {min_voltage}",
        "outFields": "VOLTAGE,OWNER,SUB_1,SUB_2,SHAPE__Len",
        "f": "geojson",
        "resultRecordCount": 5000,
        "outSR": 4326,
    }

    logger.info(f"Downloading {min_voltage}kV+ transmission lines from HIFLD...")
    try:
        resp = requests.get(url, params=params, timeout=120)
        resp.raise_for_status()
        geojson = resp.json()

        cache_path.parent.mkdir(parents=True, exist_ok=True)
        with open(cache_path, "w") as f:
            json.dump(geojson, f)

        feature_count = len(geojson.get("features", []))
        logger.info(f"Downloaded {feature_count} transmission line features")
        return geojson

    except Exception as e:
        logger.warning(f"Failed to download transmission lines: {e}")
        return {"type": "FeatureCollection", "features": []}


def download_zone_boundaries(
    cache_path: Path,
    territory_oids: dict[str, list[int]],
    zone_property: str = "iso_zone",
    force: bool = False,
) -> dict:
    """
    Download zone boundary polygons from HIFLD service territories.

    Args:
        cache_path: Path to cache the GeoJSON result
        territory_oids: {zone_code: [OBJECTID, ...]} mapping
        force: Force re-download

    Returns:
        GeoJSON FeatureCollection with zone_code as property on each feature.
    """
    if cache_path.exists() and not force:
        logger.info(f"Loading cached zone boundaries from {cache_path}")
        with open(cache_path) as f:
            return json.load(f)

    all_oids = []
    oid_to_zone = {}
    for zone, oids in territory_oids.items():
        for oid in oids:
            all_oids.append(oid)
            oid_to_zone[oid] = zone

    if not all_oids:
        logger.warning("No territory OIDs configured, skipping boundary download")
        return {"type": "FeatureCollection", "features": []}

    oid_list = ",".join(str(o) for o in all_oids)
    where = f"OBJECTID IN ({oid_list})"

    logger.info(
        f"Downloading zone boundaries for {len(territory_oids)} zones "
        f"({len(all_oids)} territories)..."
    )

    params = {
        "where": where,
        "outFields": "OBJECTID,NAME,STATE",
        "f": "geojson",
        "outSR": 4326,
    }

    try:
        resp = requests.get(
            f"{HIFLD_TERRITORY_URL}/query", params=params, timeout=120
        )
        resp.raise_for_status()
        geojson = resp.json()

        for feat in geojson.get("features", []):
            oid = feat["properties"].get("OBJECTID")
            feat["properties"][zone_property] = oid_to_zone.get(oid, "")

        cache_path.parent.mkdir(parents=True, exist_ok=True)
        with open(cache_path, "w") as f:
            json.dump(geojson, f)

        logger.info(
            f"Downloaded {len(geojson.get('features', []))} "
            f"zone boundary polygons"
        )
        return geojson

    except Exception as e:
        logger.warning(f"Failed to download zone boundaries: {e}")
        return {"type": "FeatureCollection", "features": []}
