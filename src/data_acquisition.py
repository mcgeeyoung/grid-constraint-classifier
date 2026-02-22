"""
Data acquisition and caching for PJM grid constraint analysis.

Pulls LMP data from PJM Data Miner 2 API and caches as parquet.
Provides zone centroids and data center locations as static data.
Downloads transmission line GeoJSON from HIFLD.
"""

import os
import json
import logging
import re
import random
import time
from pathlib import Path
from typing import Optional

import pandas as pd
import requests

from .pjm_client import PJMClient

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent / "data"


def _get_client() -> PJMClient:
    key = os.environ.get("PJM_SUBSCRIPTION_KEY", "")
    if not key:
        raise ValueError("PJM_SUBSCRIPTION_KEY environment variable not set")
    return PJMClient(key)


# ── Zone centroids (approximate lat/lon for map display) ──

ZONE_CENTROIDS = {
    "AECO":    {"lat": 39.45, "lon": -74.75, "name": "Atlantic City Electric"},
    "AEP":     {"lat": 38.80, "lon": -82.00, "name": "American Electric Power"},
    "APS":     {"lat": 40.00, "lon": -79.50, "name": "Allegheny Power"},
    "ATSI":    {"lat": 41.10, "lon": -81.50, "name": "FirstEnergy Ohio"},
    "BGE":     {"lat": 39.30, "lon": -76.60, "name": "Baltimore Gas & Electric"},
    "COMED":   {"lat": 41.85, "lon": -87.90, "name": "Commonwealth Edison"},
    "DAY":     {"lat": 39.76, "lon": -84.19, "name": "Dayton Power & Light"},
    "DEOK":    {"lat": 39.10, "lon": -84.50, "name": "Duke Energy Ohio/KY"},
    "DOM":     {"lat": 37.55, "lon": -78.00, "name": "Dominion Virginia"},
    "DPL":     {"lat": 39.15, "lon": -75.52, "name": "Delmarva Power"},
    "DUQ":     {"lat": 40.45, "lon": -79.95, "name": "Duquesne Light"},
    "EKPC":    {"lat": 38.20, "lon": -84.90, "name": "East Kentucky Power"},
    "JCPL":    {"lat": 40.25, "lon": -74.25, "name": "Jersey Central P&L"},
    "METED":   {"lat": 40.33, "lon": -76.00, "name": "Met-Ed"},
    "PECO":    {"lat": 40.00, "lon": -75.15, "name": "PECO Energy"},
    "PENELEC": {"lat": 41.00, "lon": -78.50, "name": "Penn Electric"},
    "PEPCO":   {"lat": 38.90, "lon": -77.00, "name": "Pepco (DC/MD)"},
    "PPL":     {"lat": 40.60, "lon": -76.00, "name": "PPL Electric"},
    "PSEG":    {"lat": 40.73, "lon": -74.17, "name": "PSE&G"},
    "RECO":    {"lat": 41.05, "lon": -74.13, "name": "Rockland Electric"},
    "PE":      {"lat": 40.33, "lon": -76.00, "name": "Penn Electric (alt)"},
}

# Key data center cluster locations in PJM (NoVA dominates)
DATA_CENTER_LOCATIONS = [
    {"name": "Ashburn, VA (NoVA)", "lat": 39.04, "lon": -77.49,
     "zone": "DOM", "notes": "Largest DC cluster globally, ~70% of internet traffic"},
    {"name": "Manassas, VA", "lat": 38.75, "lon": -77.47,
     "zone": "DOM", "notes": "Growing DC cluster, Dominion zone"},
    {"name": "Sterling, VA", "lat": 39.01, "lon": -77.43,
     "zone": "DOM", "notes": "Major DC corridor along Route 28"},
    {"name": "Elk Grove Village, IL", "lat": 42.00, "lon": -87.97,
     "zone": "COMED", "notes": "Chicago metro DC hub"},
    {"name": "Newark, NJ", "lat": 40.74, "lon": -74.17,
     "zone": "PSEG", "notes": "NJ financial/cloud DC cluster"},
    {"name": "Secaucus, NJ", "lat": 40.79, "lon": -74.06,
     "zone": "PSEG", "notes": "NYC-adjacent DC facilities"},
]


# ── Zone boundary polygons from HIFLD service territories ──

HIFLD_TERRITORY_URL = (
    "https://services3.arcgis.com/OYP7N6mAJJCyH6hd/arcgis/rest/services/"
    "Electric_Retail_Service_Territories_HIFLD/FeatureServer/0"
)

# PJM zone → HIFLD OBJECTID(s) for the primary utility in each zone.
# Some zones map to multiple utility service territories (e.g., AEP sub-companies).
ZONE_TERRITORY_OIDS = {
    "AECO":    [2876],   # Atlantic City Electric Co
    "AEP":     [2585, 649, 2844],  # Appalachian Power, Ohio Power, Indiana Michigan Power
    "APS":     [1601],   # West Penn Power (Allegheny Power System)
    "ATSI":    [648, 2015, 1388],  # Ohio Edison, Cleveland Elec Illum, Toledo Edison
    "BGE":     [277],    # Baltimore Gas & Electric
    "COMED":   [2117],   # Commonwealth Edison
    "DAY":     [2211],   # Dayton Power & Light
    "DEOK":    [1989],   # Duke Energy Ohio
    "DOM":     [1504],   # Virginia Electric & Power (Dominion)
    "DPL":     [2226],   # Delmarva Power
    "DUQ":     [2270],   # Duquesne Light
    "JCPL":    [2892],   # Jersey Central Power & Light
    "METED":   [357],    # Metropolitan Edison
    "PECO":    [793],    # PECO Energy
    "PENELEC": [772],    # Pennsylvania Electric
    "PEPCO":   [845],    # Potomac Electric Power
    "PPL":     [774],    # PPL Electric Utilities
    "PSEG":    [885],    # Public Service Electric & Gas
    "RECO":    [973],    # Rockland Electric
}

ZONE_BOUNDARIES_CACHE = DATA_DIR / "geo" / "zone_boundaries.json"


def download_zone_boundaries(force: bool = False) -> dict:
    """
    Download PJM zone boundary polygons from HIFLD Electric Retail Service
    Territories. Returns GeoJSON FeatureCollection with zone name as a
    property on each feature.

    Cached to data/geo/zone_boundaries.json.
    """
    if ZONE_BOUNDARIES_CACHE.exists() and not force:
        logger.info(f"Loading cached zone boundaries from {ZONE_BOUNDARIES_CACHE}")
        with open(ZONE_BOUNDARIES_CACHE) as f:
            return json.load(f)

    all_oids = []
    oid_to_zone = {}
    for zone, oids in ZONE_TERRITORY_OIDS.items():
        for oid in oids:
            all_oids.append(oid)
            oid_to_zone[oid] = zone

    oid_list = ",".join(str(o) for o in all_oids)
    where = f"OBJECTID IN ({oid_list})"

    logger.info(f"Downloading zone boundaries for {len(ZONE_TERRITORY_OIDS)} zones ({len(all_oids)} territories)...")

    params = {
        "where": where,
        "outFields": "OBJECTID,NAME,STATE",
        "f": "geojson",
        "outSR": 4326,
    }

    try:
        resp = requests.get(f"{HIFLD_TERRITORY_URL}/query", params=params, timeout=120)
        resp.raise_for_status()
        geojson = resp.json()

        # Tag each feature with its PJM zone name
        for feat in geojson.get("features", []):
            oid = feat["properties"].get("OBJECTID")
            feat["properties"]["pjm_zone"] = oid_to_zone.get(oid, "")

        ZONE_BOUNDARIES_CACHE.parent.mkdir(parents=True, exist_ok=True)
        with open(ZONE_BOUNDARIES_CACHE, "w") as f:
            json.dump(geojson, f)

        logger.info(f"Downloaded {len(geojson.get('features', []))} zone boundary polygons")
        return geojson

    except Exception as e:
        logger.warning(f"Failed to download zone boundaries: {e}")
        return {"type": "FeatureCollection", "features": []}


# ── Geocoding support for pnode map layer ──

ZONE_STATE_MAP = {
    "AECO": "NJ", "COMED": "IL", "DOM": "VA", "DPL": "DE",
    "JCPL": "NJ", "OVEC": "OH", "PECO": "PA", "PEPCO": "MD",
    "PPL": "PA", "PSEG": "NJ", "RECO": "NJ",
    "AEP": "OH", "APS": "PA", "ATSI": "OH", "BGE": "MD",
    "DAY": "OH", "DEOK": "OH", "DUQ": "PA", "EKPC": "KY",
    "METED": "PA", "PENELEC": "PA", "PE": "PA",
}

GEOCODE_CACHE_PATH = DATA_DIR / "geo" / "pnode_coordinates.json"


def _clean_pnode_name(name: str) -> str:
    """
    Clean a PJM pnode name for geocoding.
    Strip trailing digits (CHESTER4 -> CHESTER), remove leading number
    prefixes ('72 GOOSE' -> 'GOOSE', '958_HOGR' -> 'HOGR').
    """
    cleaned = name.strip()
    # Remove leading numeric prefix with space or underscore separator
    cleaned = re.sub(r"^\d+[\s_]+", "", cleaned)
    # Strip trailing digits
    cleaned = re.sub(r"\d+$", "", cleaned)
    cleaned = cleaned.strip("_ ")
    if len(cleaned) < 2:
        return name.strip()
    return cleaned


def _geocode_single(name: str, state: str, session: requests.Session) -> Optional[dict]:
    """
    Geocode a single pnode name via Nominatim (OpenStreetMap).
    Returns {lat, lon, matched_name} or None.
    """
    query = f"{name}, {state}, USA"
    url = "https://nominatim.openstreetmap.org/search"
    params = {
        "q": query,
        "format": "json",
        "limit": 1,
        "countrycodes": "us",
    }
    headers = {"User-Agent": "grid-constraint-classifier/1.0 (pnode geocoding)"}
    try:
        resp = session.get(url, params=params, headers=headers, timeout=10)
        resp.raise_for_status()
        results = resp.json()
        if results:
            return {
                "lat": float(results[0]["lat"]),
                "lon": float(results[0]["lon"]),
                "matched_name": results[0].get("display_name", ""),
            }
    except Exception as e:
        logger.debug(f"Geocode failed for '{query}': {e}")
    return None


def geocode_pnodes(pnode_results: dict) -> dict:
    """
    Geocode all unique pnode names from pnode drill-down results.

    Uses Nominatim with 1 req/sec rate limit. Results cached to
    data/geo/pnode_coordinates.json for instant reuse.

    Args:
        pnode_results: {zone: analysis_dict} from analyze_all_constrained_zones()

    Returns:
        {pnode_name: {lat, lon, source, matched_name}} for every pnode name.
    """
    # Load existing cache
    cache = {}
    if GEOCODE_CACHE_PATH.exists():
        with open(GEOCODE_CACHE_PATH) as f:
            cache = json.load(f)
        logger.info(f"Loaded {len(cache)} cached pnode coordinates")

    # Collect unique names with their zone context
    name_zone = {}  # {pnode_name: zone}
    for zone, analysis in pnode_results.items():
        for pnode in analysis.get("all_scored", []):
            pname = pnode["pnode_name"]
            if pname not in name_zone:
                name_zone[pname] = zone

    # Find names not yet cached
    to_geocode = {n: z for n, z in name_zone.items() if n not in cache}
    logger.info(
        f"Pnode geocoding: {len(name_zone)} unique names, "
        f"{len(cache)} cached, {len(to_geocode)} to geocode"
    )

    if to_geocode:
        session = requests.Session()
        geocoded = 0
        fallback = 0

        for i, (pname, zone) in enumerate(to_geocode.items()):
            state = ZONE_STATE_MAP.get(zone, "")
            cleaned = _clean_pnode_name(pname)

            result = _geocode_single(cleaned, state, session)
            if result:
                cache[pname] = {
                    "lat": result["lat"],
                    "lon": result["lon"],
                    "source": "nominatim",
                    "matched_name": result["matched_name"],
                }
                geocoded += 1
            else:
                # Fall back to jittered zone centroid
                centroid = ZONE_CENTROIDS.get(zone, {"lat": 39.5, "lon": -78.0})
                cache[pname] = {
                    "lat": centroid["lat"] + random.uniform(-0.15, 0.15),
                    "lon": centroid["lon"] + random.uniform(-0.15, 0.15),
                    "source": "zone_centroid",
                    "matched_name": "",
                }
                fallback += 1

            # Progress logging every 50
            if (i + 1) % 50 == 0:
                logger.info(f"  Geocoded {i + 1}/{len(to_geocode)} pnodes...")

            # Rate limit: 1 request per second for Nominatim
            time.sleep(1.0)

        logger.info(
            f"Geocoding complete: {geocoded} matched, {fallback} fell back to zone centroid"
        )

        # Save updated cache
        GEOCODE_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(GEOCODE_CACHE_PATH, "w") as f:
            json.dump(cache, f, indent=2)
        logger.info(f"Saved {len(cache)} coordinates to {GEOCODE_CACHE_PATH}")

    # Return only the names we need
    return {n: cache[n] for n in name_zone if n in cache}


def pull_zone_lmps(year: int = 2025, force: bool = False) -> pd.DataFrame:
    """
    Pull zone-level day-ahead hourly LMPs for a full year.
    Caches result as parquet. ~5 API calls, ~60s.
    """
    cache_path = DATA_DIR / "zone_lmps" / f"zone_lmps_{year}.parquet"

    if cache_path.exists() and not force:
        logger.info(f"Loading cached zone LMPs from {cache_path}")
        return pd.read_parquet(cache_path)

    client = _get_client()
    date_range = f"1/1/{year} 00:00to12/31/{year} 23:00"

    logger.info(f"Pulling zone LMPs for {year} (date range: {date_range})")
    df = client.query_lmps(
        datetime_beginning_ept=date_range,
        lmp_type="ZONE",
    )

    if len(df) == 0:
        logger.warning("No zone LMP data returned")
        return df

    # Parse datetime
    df["datetime_beginning_ept"] = pd.to_datetime(df["datetime_beginning_ept"])
    df["hour"] = df["datetime_beginning_ept"].dt.hour
    df["month"] = df["datetime_beginning_ept"].dt.month
    df["day_of_week"] = df["datetime_beginning_ept"].dt.dayofweek

    # Ensure numeric columns
    for col in ["system_energy_price_da", "total_lmp_da", "congestion_price_da", "marginal_loss_price_da"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(cache_path, index=False)
    logger.info(f"Cached {len(df)} rows to {cache_path}")

    return df


def pull_pnode_list(zone: Optional[str] = None, force: bool = False) -> pd.DataFrame:
    """Pull pnode definitions, optionally filtered by zone."""
    suffix = f"_{zone}" if zone else "_all"
    cache_path = DATA_DIR / "pnodes" / f"pnodes{suffix}.parquet"

    if cache_path.exists() and not force:
        logger.info(f"Loading cached pnodes from {cache_path}")
        return pd.read_parquet(cache_path)

    client = _get_client()
    logger.info(f"Pulling pnode list (zone={zone})")
    df = client.query_pnodes(zone=zone)

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(cache_path, index=False)
    logger.info(f"Cached {len(df)} pnodes to {cache_path}")

    return df


def pull_node_lmps(
    zone: str = "DOM",
    year: int = 2025,
    month: int = 6,
    force: bool = False,
) -> pd.DataFrame:
    """
    Pull node-level LMPs for a specific zone and month.
    More granular than zone-level, useful for identifying specific constraint locations.
    """
    cache_path = DATA_DIR / "node_lmps" / f"node_lmps_{zone}_{year}_{month:02d}.parquet"

    if cache_path.exists() and not force:
        logger.info(f"Loading cached node LMPs from {cache_path}")
        return pd.read_parquet(cache_path)

    client = _get_client()
    # Get last day of month
    import calendar
    last_day = calendar.monthrange(year, month)[1]
    date_range = f"{month}/1/{year} 00:00to{month}/{last_day}/{year} 23:00"

    logger.info(f"Pulling node LMPs for {zone} {year}-{month:02d}")
    df = client.query_lmps(
        datetime_beginning_ept=date_range,
        lmp_type="GEN",
        zone=zone,
    )

    if len(df) > 0:
        df["datetime_beginning_ept"] = pd.to_datetime(df["datetime_beginning_ept"])
        for col in ["total_lmp_da", "congestion_price_da", "marginal_loss_price_da"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(cache_path, index=False)
    logger.info(f"Cached {len(df)} rows to {cache_path}")

    return df


def pull_node_lmps_year(
    zone: str,
    year: int = 2025,
    force: bool = False,
) -> pd.DataFrame:
    """
    Pull node-level LMPs for a zone across all 12 months.
    Reuses pull_node_lmps() per month (each cached individually as parquet).
    Returns concatenated DataFrame for the full year.
    """
    frames = []
    for month in range(1, 13):
        df = pull_node_lmps(zone=zone, year=year, month=month, force=force)
        if len(df) > 0:
            frames.append(df)

    if not frames:
        logger.warning(f"No node LMP data for {zone} {year}")
        return pd.DataFrame()

    combined = pd.concat(frames, ignore_index=True)
    logger.info(f"Combined {len(combined)} node LMP rows for {zone} {year} (12 months)")
    return combined


def pull_constrained_zone_pnodes(
    classification_summary: dict,
    year: int = 2025,
    force: bool = False,
) -> dict:
    """
    Pull pnode lists and node LMPs for all constrained zones.

    Args:
        classification_summary: Pipeline summary dict with "classifications" key
        year: Year for LMP data
        force: Force re-download even if cached

    Returns:
        Dict of {zone: DataFrame} with full-year node LMPs for constrained zones.
    """
    constrained_zones = []
    zone_scores = classification_summary.get("zone_scores", [])
    for zs in zone_scores:
        t = zs.get("transmission_score", 0)
        g = zs.get("generation_score", 0)
        if t >= 0.5 or g >= 0.5:
            constrained_zones.append(zs["zone"])

    logger.info(f"Constrained zones for pnode drill-down: {constrained_zones}")

    zone_data = {}
    for zone in constrained_zones:
        try:
            # Pull pnode metadata (name, type, voltage) - optional, non-blocking
            try:
                pnodes = pull_pnode_list(zone=zone, force=force)
                logger.info(f"  {zone}: {len(pnodes)} pnodes")
            except Exception as e:
                logger.warning(f"  {zone}: could not pull pnode list ({e}), continuing with LMP data only")

            # Pull full-year node LMPs
            node_lmps = pull_node_lmps_year(zone=zone, year=year, force=force)
            if len(node_lmps) > 0:
                zone_data[zone] = node_lmps
            else:
                logger.warning(f"  {zone}: no node LMP data, skipping")
        except Exception as e:
            logger.warning(f"  {zone}: failed to pull node LMP data ({e}), skipping")

    logger.info(f"Pulled pnode data for {len(zone_data)} zones")
    return zone_data


def download_transmission_lines(force: bool = False) -> dict:
    """
    Download PJM-area transmission lines (230kV+) from HIFLD FeatureServer.
    Returns GeoJSON dict. Not rate-limited (different API).
    """
    cache_path = DATA_DIR / "geo" / "transmission_lines_230kv.json"

    if cache_path.exists() and not force:
        logger.info(f"Loading cached transmission lines from {cache_path}")
        with open(cache_path) as f:
            return json.load(f)

    # HIFLD Electric Power Transmission Lines FeatureServer
    # Filter: VOLTAGE >= 230 AND STATE in PJM states
    pjm_states = "('VA','MD','DC','PA','NJ','DE','OH','WV','NC','IN','IL','MI','KY','TN')"
    url = (
        "https://services1.arcgis.com/Hp6G80Pky0om7QvQ/arcgis/rest/services/"
        "Electric_Power_Transmission_Lines/FeatureServer/0/query"
    )
    params = {
        "where": "VOLTAGE >= 230",
        "outFields": "VOLTAGE,OWNER,SUB_1,SUB_2,SHAPE__Len",
        "f": "geojson",
        "resultRecordCount": 5000,
        "outSR": 4326,
    }

    logger.info("Downloading 230kV+ transmission lines from HIFLD...")
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
        # Return empty GeoJSON on failure (non-critical)
        return {"type": "FeatureCollection", "features": []}


def get_zone_centroids() -> dict:
    """Return PJM zone centroid coordinates."""
    return ZONE_CENTROIDS


def get_data_center_locations() -> list:
    """Return known data center cluster locations in PJM."""
    return DATA_CENTER_LOCATIONS


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    # Quick test: pull one day of zone LMPs
    df = pull_zone_lmps(year=2025)
    print(f"Zone LMPs: {len(df)} rows")
    print(df.head())
