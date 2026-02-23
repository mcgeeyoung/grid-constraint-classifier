"""
Shared Nominatim geocoding utilities for pnodes and data centers.

Rate limit: 1 request per second (Nominatim terms of use).
Supports caching to avoid re-geocoding on repeat runs.
"""

import json
import logging
import random
import re
import time
from pathlib import Path
from typing import Optional

import requests

logger = logging.getLogger(__name__)


def geocode_single(
    session: requests.Session,
    query: str,
    timeout: int = 10,
) -> Optional[tuple[float, float]]:
    """
    Geocode a single query via Nominatim.

    Returns (lat, lon) or None.
    """
    try:
        resp = session.get(
            "https://nominatim.openstreetmap.org/search",
            params={
                "q": query,
                "format": "json",
                "limit": 1,
                "countrycodes": "us",
            },
            headers={
                "User-Agent": "grid-constraint-classifier/2.0 (geocoding)",
            },
            timeout=timeout,
        )
        resp.raise_for_status()
        results = resp.json()
        if results:
            return (float(results[0]["lat"]), float(results[0]["lon"]))
    except Exception as e:
        logger.debug(f"Geocode failed for '{query}': {e}")
    return None


def clean_pnode_name(name: str) -> str:
    """
    Clean a pnode name for geocoding.

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


def geocode_pnodes(
    pnode_results: dict,
    zone_state_map: dict,
    zone_centroids: dict,
    cache_path: Path,
) -> dict:
    """
    Geocode all unique pnode names from pnode drill-down results.

    Args:
        pnode_results: {zone: analysis_dict} from analyze_all_constrained_zones()
        zone_state_map: {zone: primary_state_code} for geocoding context
        zone_centroids: {zone: {lat, lon, name}} for fallback
        cache_path: Path to coordinate cache JSON

    Returns:
        {pnode_name: {lat, lon, source, matched_name}}
    """
    # Load existing cache
    cache = {}
    if cache_path.exists():
        with open(cache_path) as f:
            cache = json.load(f)
        logger.info(f"Loaded {len(cache)} cached pnode coordinates")

    # Collect unique names with their zone context
    name_zone = {}
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
            state = zone_state_map.get(zone, "")
            cleaned = clean_pnode_name(pname)

            result = geocode_single(session, f"{cleaned}, {state}, USA")
            if result:
                cache[pname] = {
                    "lat": result[0],
                    "lon": result[1],
                    "source": "nominatim",
                    "matched_name": "",
                }
                geocoded += 1
            else:
                centroid = zone_centroids.get(zone, {"lat": 39.5, "lon": -78.0})
                lat = centroid["lat"] if isinstance(centroid, dict) else centroid[0]
                lon = centroid["lon"] if isinstance(centroid, dict) else centroid[1]
                cache[pname] = {
                    "lat": lat + random.uniform(-0.15, 0.15),
                    "lon": lon + random.uniform(-0.15, 0.15),
                    "source": "zone_centroid",
                    "matched_name": "",
                }
                fallback += 1

            if (i + 1) % 50 == 0:
                logger.info(f"  Geocoded {i + 1}/{len(to_geocode)} pnodes...")

            time.sleep(1.0)

        logger.info(
            f"Geocoding complete: {geocoded} matched, "
            f"{fallback} fell back to zone centroid"
        )

        cache_path.parent.mkdir(parents=True, exist_ok=True)
        with open(cache_path, "w") as f:
            json.dump(cache, f, indent=2)
        logger.info(f"Saved {len(cache)} coordinates to {cache_path}")

    return {n: cache[n] for n in name_zone if n in cache}
