"""
PJM GIS data fetcher for backbone transmission lines and zone boundaries.

Pulls geospatial data from PJM's authenticated ArcGIS MapServer at
gis.pjm.com. Requires PJM GIS credentials (username/password).

Layers used:
  - Layer 9:  Backbone Transmission Lines (345kV+ polylines)
  - Layer 17: PJM Zones (official zone boundary polygons)

Auth pattern: generate a referer-based token via the ArcGIS token
endpoint, then pass it as a URL query parameter with cookie jar and
Referer header on each request.
"""

import json
import logging
import os
import time
from pathlib import Path
from typing import Optional

import requests

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent / "data"
GEO_CACHE_DIR = DATA_DIR / "geo"

BACKBONE_CACHE = GEO_CACHE_DIR / "pjm_backbone_lines.geojson"
ZONES_CACHE = GEO_CACHE_DIR / "pjm_zone_boundaries.geojson"

# ArcGIS endpoints
TOKEN_URL = "https://gis.pjm.com/arcgis/tokens/generateToken"
MAP_SERVER = "https://gis.pjm.com/arcgis/rest/services/ESM/ESM/MapServer"
REFERER = "https://gis.pjm.com/esm/default.html"

# Layer IDs
BACKBONE_LAYER = 9
ZONES_LAYER = 17


def _get_credentials() -> tuple[str, str]:
    """
    Get PJM GIS credentials from environment variables.

    Set PJM_GIS_USERNAME and PJM_GIS_PASSWORD, or fall back to
    PJM_GIS_USER / PJM_GIS_PASS.
    """
    username = os.environ.get("PJM_GIS_USERNAME") or os.environ.get("PJM_GIS_USER", "")
    password = os.environ.get("PJM_GIS_PASSWORD") or os.environ.get("PJM_GIS_PASS", "")
    return username, password


def _generate_token(session: requests.Session) -> Optional[str]:
    """
    Generate an ArcGIS token using referer-based auth.

    Returns the token string or None on failure.
    """
    username, password = _get_credentials()
    if not username or not password:
        logger.error(
            "PJM GIS credentials not set. Export PJM_GIS_USERNAME and "
            "PJM_GIS_PASSWORD environment variables."
        )
        return None

    try:
        resp = session.post(
            TOKEN_URL,
            data={
                "username": username,
                "password": password,
                "client": "referer",
                "referer": REFERER,
                "f": "json",
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

        if "token" in data:
            return data["token"]
        if "error" in data:
            logger.error(f"Token generation failed: {data['error']}")
            return None

        logger.error(f"Unexpected token response: {data}")
        return None

    except Exception as e:
        logger.error(f"Token generation error: {e}")
        return None


def _query_layer(
    session: requests.Session,
    layer_id: int,
    where: str = "1=1",
    out_fields: str = "*",
    return_geometry: bool = True,
    max_records: int = 5000,
) -> Optional[dict]:
    """
    Query an ArcGIS MapServer layer and return GeoJSON.

    Generates a fresh token per request (tokens are short-lived).
    Uses cookie jar + Referer + token in URL for auth.
    """
    token = _generate_token(session)
    if not token:
        return None

    url = f"{MAP_SERVER}/{layer_id}/query"
    params = {
        "where": where,
        "outFields": out_fields,
        "returnGeometry": "true" if return_geometry else "false",
        "outSR": 4326,
        "f": "geojson",
        "resultRecordCount": max_records,
        "token": token,
    }

    try:
        resp = session.get(
            url,
            params=params,
            headers={"Referer": REFERER},
            timeout=120,
        )
        resp.raise_for_status()
        data = resp.json()

        if "error" in data:
            logger.error(f"Layer {layer_id} query error: {data['error']}")
            return None

        return data

    except Exception as e:
        logger.error(f"Layer {layer_id} query failed: {e}")
        return None


def _query_layer_paginated(
    session: requests.Session,
    layer_id: int,
    where: str = "1=1",
    out_fields: str = "*",
    page_size: int = 2000,
) -> Optional[dict]:
    """
    Query a layer with pagination to handle large result sets.

    ArcGIS limits results per request; this fetches in pages using
    resultOffset and merges into a single GeoJSON FeatureCollection.
    """
    all_features = []
    offset = 0

    while True:
        token = _generate_token(session)
        if not token:
            return None

        url = f"{MAP_SERVER}/{layer_id}/query"
        params = {
            "where": where,
            "outFields": out_fields,
            "returnGeometry": "true",
            "outSR": 4326,
            "f": "geojson",
            "resultRecordCount": page_size,
            "resultOffset": offset,
            "token": token,
        }

        try:
            resp = session.get(
                url,
                params=params,
                headers={"Referer": REFERER},
                timeout=120,
            )
            resp.raise_for_status()
            data = resp.json()

            if "error" in data:
                logger.error(f"Layer {layer_id} page query error: {data['error']}")
                break

            features = data.get("features", [])
            all_features.extend(features)
            logger.info(f"  Layer {layer_id}: fetched {len(features)} features (offset {offset})")

            # If we got fewer than page_size, we've reached the end
            if len(features) < page_size:
                break

            offset += page_size
            time.sleep(0.5)  # Brief delay between pages

        except Exception as e:
            logger.error(f"Layer {layer_id} paginated query failed at offset {offset}: {e}")
            break

    if not all_features:
        return None

    return {
        "type": "FeatureCollection",
        "features": all_features,
    }


def fetch_backbone_lines(force: bool = False) -> dict:
    """
    Fetch PJM backbone transmission lines (layer 9, 345kV+).

    Returns GeoJSON FeatureCollection with polyline geometries.
    Fields: NAME, VOLTAGE, MILES, COMPANY_ID, LINE_ID.

    Cached to data/geo/pjm_backbone_lines.geojson.
    """
    if BACKBONE_CACHE.exists() and not force:
        logger.info(f"Loading cached PJM backbone lines from {BACKBONE_CACHE}")
        with open(BACKBONE_CACHE) as f:
            return json.load(f)

    logger.info("Fetching PJM backbone transmission lines from GIS...")
    session = requests.Session()

    geojson = _query_layer(
        session,
        BACKBONE_LAYER,
        out_fields="*",
        max_records=5000,
    )

    if not geojson or not geojson.get("features"):
        logger.warning("No backbone line features returned")
        return {"type": "FeatureCollection", "features": []}

    # Trim properties to only the fields we need for display
    keep_fields = {"NAME", "VOLTAGE", "MILES", "COMPANY_ID", "LINE_ID", "SYM_CODE"}
    for feat in geojson.get("features", []):
        props = feat.get("properties", {})
        feat["properties"] = {k: v for k, v in props.items() if k in keep_fields}
        # Ensure NAME has a usable value (some are blank)
        if not (feat["properties"].get("NAME") or "").strip():
            feat["properties"]["NAME"] = feat["properties"].get("LINE_ID", "Unknown")

    # Cache result
    GEO_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with open(BACKBONE_CACHE, "w") as f:
        json.dump(geojson, f)

    count = len(geojson["features"])
    logger.info(f"Fetched {count} PJM backbone transmission lines")
    return geojson


def fetch_zone_boundaries(force: bool = False) -> dict:
    """
    Fetch official PJM zone boundary polygons (layer 17).

    Returns GeoJSON FeatureCollection with polygon geometries.
    Fields: COMMERCIAL_ZONE, PLANNING_ZONE_NAME, ZONE_ID.

    Cached to data/geo/pjm_zone_boundaries.geojson.
    """
    if ZONES_CACHE.exists() and not force:
        logger.info(f"Loading cached PJM zone boundaries from {ZONES_CACHE}")
        with open(ZONES_CACHE) as f:
            return json.load(f)

    logger.info("Fetching PJM zone boundaries from GIS...")
    session = requests.Session()

    geojson = _query_layer(
        session,
        ZONES_LAYER,
        out_fields="*",
        max_records=100,
    )

    if not geojson or not geojson.get("features"):
        logger.warning("No zone boundary features returned")
        return {"type": "FeatureCollection", "features": []}

    # Normalize zone names to match our zone code convention
    zone_name_map = _build_zone_name_map()
    for feat in geojson.get("features", []):
        props = feat.get("properties", {})
        commercial = props.get("COMMERCIAL_ZONE", "")
        planning = props.get("PLANNING_ZONE_NAME", "")

        # Map the PJM commercial zone name to our zone codes
        zone_code = zone_name_map.get(commercial, "")
        if not zone_code:
            zone_code = zone_name_map.get(planning, "")
        props["pjm_zone"] = zone_code
        props["NAME"] = planning or commercial

    # Cache result
    GEO_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with open(ZONES_CACHE, "w") as f:
        json.dump(geojson, f)

    count = len(geojson["features"])
    logger.info(f"Fetched {count} PJM zone boundary polygons")
    return geojson


def _build_zone_name_map() -> dict:
    """
    Map PJM GIS zone names to our zone code convention.

    PJM GIS uses full utility names (e.g., "Virginia Electric and Power Co.")
    while our pipeline uses short codes (e.g., "DOM").
    """
    return {
        # COMMERCIAL_ZONE values from PJM GIS layer 17
        "Baltimore Gas and Electric Company": "BGE",
        "Delmarva Power and Light Company": "DPL",
        "Duquesne Light Company": "DUQ",
        "Jersey Central Power and Light Company": "JCPL",
        "Rockland Electric Company": "RECO",
        "Commonwealth Edison Company": "COMED",
        "The Dayton Power and Light Co.": "DAY",
        "Pennsylvania Electric Company": "PENELEC",
        "Metropolitan Edison Company": "METED",
        "PPL Electric Utilities Corporation": "PPL",
        "Atlantic City Electric Company": "AECO",
        "PECO Energy Company": "PECO",
        "Public Service Electric and Gas Company": "PSEG",
        "Potomac Electric Power Company": "PEPCO",
        "Virginia Electric and Power Co.": "DOM",
        "Allegheny Power": "APS",
        "American Transmission Systems, Inc.": "ATSI",
        "Duke Energy Ohio Kentucky": "DEOK",
        "American Electric Power Co., Inc.": "AEP",
        "Eastern Kentucky Power Cooperative": "EKPC",
        "Ohio Valley Electric Corporation": "OVEC",
        # PLANNING_ZONE_NAME values (shorter forms)
        "BGE": "BGE",
        "DPL": "DPL",
        "DL": "DUQ",
        "JCPL": "JCPL",
        "RE": "RECO",
        "ComEd": "COMED",
        "Dayton": "DAY",
        "PENELEC": "PENELEC",
        "ME": "METED",
        "PPL": "PPL",
        "AEC": "AECO",
        "PECO": "PECO",
        "PSEG": "PSEG",
        "PEPCO": "PEPCO",
        "Dominion": "DOM",
        "APS": "APS",
        "ATSI": "ATSI",
        "DEOK": "DEOK",
        "AEP": "AEP",
        "EKPC": "EKPC",
        "OVEC HQ": "OVEC",
    }


def load_pjm_gis_data() -> tuple[dict, dict]:
    """
    Load cached PJM GIS data (backbone lines + zone boundaries).

    Returns (backbone_geojson, zones_geojson) or empty defaults.
    """
    backbone = {"type": "FeatureCollection", "features": []}
    zones = {"type": "FeatureCollection", "features": []}

    if BACKBONE_CACHE.exists():
        with open(BACKBONE_CACHE) as f:
            backbone = json.load(f)
        logger.info(f"Loaded {len(backbone.get('features', []))} cached PJM backbone lines")

    if ZONES_CACHE.exists():
        with open(ZONES_CACHE) as f:
            zones = json.load(f)
        logger.info(f"Loaded {len(zones.get('features', []))} cached PJM zone boundaries")

    return backbone, zones
