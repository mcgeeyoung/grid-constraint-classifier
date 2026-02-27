"""
PG&E GRIP (Grid Relief through Integrated Programs) substation data fetcher.

Pulls distribution substation loading data from PG&E's DRP Compliance
ArcGIS FeatureServer with point geometry for geographic matching.
Also fetches division boundary polygons from the GNASubAreaView layer.

Follows the same cache-first pattern as scraping/hifld.py.
"""

import json
import logging
import math
from pathlib import Path

import pandas as pd
import requests

logger = logging.getLogger(__name__)

GRIP_URL = (
    "https://services2.arcgis.com/mJaJSax0KPHoCNB6/ArcGIS/rest/services/"
    "DRPComplianceRelProd/FeatureServer/31/query"
)

# GNASubAreaView layer (polygon features with division field)
GNA_SUBAREA_URL = (
    "https://services2.arcgis.com/mJaJSax0KPHoCNB6/ArcGIS/rest/services/"
    "DRPComplianceRelProd/FeatureServer/15/query"
)

LOAD_PROFILE_URL = (
    "https://services2.arcgis.com/mJaJSax0KPHoCNB6/ArcGIS/rest/services/"
    "DRPComplianceRelProd/FeatureServer/25/query"
)

GRIP_FIELDS = [
    "substationname",
    "bankname",
    "division",
    "facilityratingmw",
    "facilityloadingmw2025",
    "peakfacilityloadingpercent",
    "facilitytype",
]

PAGE_SIZE = 2000


def _web_mercator_to_wgs84(x: float, y: float) -> tuple[float, float]:
    """Convert Web Mercator (EPSG:3857) coordinates to WGS84 lat/lon."""
    lon = x / 20037508.34 * 180.0
    lat = math.atan(math.exp(y / 20037508.34 * math.pi)) * 360.0 / math.pi - 90.0
    return lat, lon


def fetch_grip_substations(
    cache_path: Path,
    force: bool = False,
) -> pd.DataFrame:
    """
    Fetch PG&E GRIP substation data with geometry from ArcGIS FeatureServer.

    Args:
        cache_path: Path to cache CSV
        force: Re-download even if cache exists

    Returns:
        DataFrame with substation data, sub_clean column, and lat/lon.
    """
    if cache_path.exists() and not force:
        logger.info(f"Loading cached GRIP substations from {cache_path}")
        df = pd.read_csv(cache_path)
        logger.info(f"Loaded {len(df)} GRIP bank records")
        return df

    logger.info("Fetching PG&E GRIP substation data from ArcGIS...")
    session = requests.Session()
    session.headers.update({"User-Agent": "grid-constraint-classifier/1.0"})

    all_features = []
    offset = 0

    while True:
        params = {
            "where": "1=1",
            "outFields": ",".join(GRIP_FIELDS),
            "returnGeometry": "true",
            "f": "json",
            "resultRecordCount": PAGE_SIZE,
            "resultOffset": offset,
        }

        try:
            resp = session.get(GRIP_URL, params=params, timeout=60)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.error(f"GRIP fetch failed at offset {offset}: {e}")
            break

        features = data.get("features", [])
        if not features:
            break

        all_features.extend(features)
        logger.info(f"  Fetched {len(all_features)} features (offset {offset})...")

        if len(features) < PAGE_SIZE:
            break
        offset += PAGE_SIZE

    if not all_features:
        logger.warning("No GRIP features returned")
        return pd.DataFrame()

    # Parse attributes and geometry
    records = []
    for feat in all_features:
        attrs = feat.get("attributes", {})
        geom = feat.get("geometry", {})
        row = {k: attrs.get(k) for k in GRIP_FIELDS}

        # Convert Web Mercator to WGS84
        x = geom.get("x")
        y = geom.get("y")
        if x is not None and y is not None:
            lat, lon = _web_mercator_to_wgs84(x, y)
            row["lat"] = round(lat, 6)
            row["lon"] = round(lon, 6)
        else:
            row["lat"] = None
            row["lon"] = None

        records.append(row)

    df = pd.DataFrame(records)

    # Add cleaned substation name for matching
    df["sub_clean"] = (
        df["substationname"]
        .fillna("")
        .str.strip()
        .str.upper()
    )

    # Cache
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(cache_path, index=False)
    logger.info(
        f"Cached {len(df)} GRIP bank records to {cache_path} "
        f"({df['sub_clean'].nunique()} unique substations, "
        f"{df['division'].nunique()} divisions)"
    )

    return df


def fetch_substation_load_profiles(
    cache_path: Path,
    force: bool = False,
) -> pd.DataFrame:
    """
    Fetch PG&E GRIP substation hourly load profiles from ArcGIS FeatureServer.

    Layer 25 (SubstationLoadProfile) contains 288 rows per substation
    (12 months x 24 hours) with low/high load values in kW.

    Args:
        cache_path: Path to cache CSV
        force: Re-download even if cache exists

    Returns:
        DataFrame with columns: subname, subid, month, hour, low, high
    """
    if cache_path.exists() and not force:
        logger.info(f"Loading cached load profiles from {cache_path}")
        return pd.read_csv(cache_path)

    logger.info("Fetching PG&E GRIP substation load profiles from ArcGIS...")
    session = requests.Session()
    session.headers.update({"User-Agent": "grid-constraint-classifier/1.0"})

    all_features = []
    offset = 0

    while True:
        params = {
            "where": "1=1",
            "outFields": "subname,subid,monthhour,low,high",
            "f": "json",
            "resultRecordCount": PAGE_SIZE,
            "resultOffset": offset,
        }

        try:
            resp = session.get(LOAD_PROFILE_URL, params=params, timeout=120)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.error(f"Load profile fetch failed at offset {offset}: {e}")
            break

        features = data.get("features", [])
        if not features:
            break

        all_features.extend(features)
        logger.info(f"  Fetched {len(all_features)} load profile records (offset {offset})...")

        if len(features) < PAGE_SIZE:
            break
        offset += PAGE_SIZE

    if not all_features:
        logger.warning("No load profile features returned")
        return pd.DataFrame()

    records = []
    for feat in all_features:
        attrs = feat.get("attributes", {})
        monthhour = attrs.get("monthhour", "")
        if not monthhour or "_" not in monthhour:
            continue
        parts = monthhour.split("_")
        try:
            month = int(parts[0])
            hour = int(parts[1])
        except (ValueError, IndexError):
            continue

        records.append({
            "subname": (attrs.get("subname") or "").strip().upper(),
            "subid": attrs.get("subid"),
            "month": month,
            "hour": hour,
            "low": attrs.get("low", 0),
            "high": attrs.get("high", 0),
        })

    df = pd.DataFrame(records)

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(cache_path, index=False)
    logger.info(
        f"Cached {len(df)} load profile records to {cache_path} "
        f"({df['subname'].nunique()} unique substations)"
    )

    return df


def _convert_ring(ring: list[list[float]]) -> list[list[float]]:
    """Convert a polygon ring from Web Mercator to WGS84 [lon, lat] pairs."""
    converted = []
    for pt in ring:
        if len(pt) >= 2:
            lat, lon = _web_mercator_to_wgs84(pt[0], pt[1])
            converted.append([round(lon, 6), round(lat, 6)])
    return converted


def fetch_division_boundaries(
    cache_path: Path,
    force: bool = False,
) -> dict:
    """
    Fetch PG&E division boundary polygons from ArcGIS GNASubAreaView layer.

    Downloads ~1,097 per-substation service area polygons and dissolves them
    by division into ~19 division boundary multipolygons using shapely.

    Args:
        cache_path: Path to cache JSON (GeoJSON FeatureCollection)
        force: Re-download even if cache exists

    Returns:
        GeoJSON FeatureCollection with one Feature per division.
        Each feature has properties: division, centroid_lat, centroid_lon.
    """
    cache_path = Path(cache_path)
    if cache_path.exists() and not force:
        logger.info(f"Loading cached division boundaries from {cache_path}")
        with open(cache_path) as f:
            return json.load(f)

    logger.info("Fetching PG&E division boundary polygons from ArcGIS...")
    session = requests.Session()
    session.headers.update({"User-Agent": "grid-constraint-classifier/1.0"})

    all_features = []
    offset = 0

    while True:
        params = {
            "where": "1=1",
            "outFields": "division",
            "returnGeometry": "true",
            "f": "json",
            "resultRecordCount": PAGE_SIZE,
            "resultOffset": offset,
        }

        try:
            resp = session.get(GNA_SUBAREA_URL, params=params, timeout=120)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.error(f"GNA SubArea fetch failed at offset {offset}: {e}")
            break

        features = data.get("features", [])
        if not features:
            break

        all_features.extend(features)
        logger.info(f"  Fetched {len(all_features)} sub-area polygons (offset {offset})...")

        if len(features) < PAGE_SIZE:
            break
        offset += PAGE_SIZE

    if not all_features:
        logger.warning("No GNA SubArea features returned")
        return {"type": "FeatureCollection", "features": []}

    logger.info(f"Fetched {len(all_features)} sub-area polygons, dissolving by division...")

    # Group polygons by division
    from shapely.geometry import shape, mapping
    from shapely.ops import unary_union

    division_polys = {}
    skipped = 0
    for feat in all_features:
        division = (feat.get("attributes", {}).get("division") or "").strip()
        if not division:
            skipped += 1
            continue

        rings = feat.get("geometry", {}).get("rings", [])
        if not rings:
            skipped += 1
            continue

        # Convert rings from Web Mercator to WGS84
        wgs_rings = [_convert_ring(ring) for ring in rings]

        # Build a shapely polygon from the converted rings
        try:
            # First ring is exterior, remaining are holes
            exterior = wgs_rings[0]
            holes = wgs_rings[1:] if len(wgs_rings) > 1 else []
            poly = shape({
                "type": "Polygon",
                "coordinates": [exterior] + holes,
            })
            if poly.is_valid:
                division_polys.setdefault(division, []).append(poly)
            else:
                # Try to fix invalid geometry
                poly = poly.buffer(0)
                if not poly.is_empty:
                    division_polys.setdefault(division, []).append(poly)
        except Exception:
            skipped += 1

    if skipped > 0:
        logger.info(f"  Skipped {skipped} features (missing division or geometry)")

    # Dissolve polygons per division
    geojson_features = []
    for division in sorted(division_polys.keys()):
        polys = division_polys[division]
        merged = unary_union(polys)
        centroid = merged.centroid

        geojson_features.append({
            "type": "Feature",
            "properties": {
                "division": division,
                "centroid_lat": round(centroid.y, 4),
                "centroid_lon": round(centroid.x, 4),
                "n_subareas": len(polys),
            },
            "geometry": mapping(merged),
        })

    result = {
        "type": "FeatureCollection",
        "features": geojson_features,
    }

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    with open(cache_path, "w") as f:
        json.dump(result, f)
    logger.info(
        f"Cached {len(geojson_features)} division boundaries to {cache_path}"
    )

    return result
