"""
PNode-to-GRIP substation matching.

Two-pass approach:
  Pass 1: Exact name matching (~23% coverage)
  Pass 2: Geographic proximity fallback for remaining substations

Each GRIP substation is assigned its nearest scored PNode so that
distribution loading data can be combined with transmission congestion.
"""

import json
import logging
import re
from math import atan2, cos, radians, sin, sqrt
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

# Manual overrides for known name mismatches
NAME_OVERRIDES = {
    "BELLHVN": "BELLE HAVEN",
    "BEARCRK": "BEAR CREEK",
    "BCKSCRK": "BUCKS CREEK",
    "BRNSWCK": "BRUNSWICK",
    "BAYMDWS": "BAY MEADOWS",
    "CHPMNRN": "CHAPMAN RANCH",
    "CNTRCST": "CONTRA COSTA",
    "EASTAVN": "EAST AVENUE",
    "FLRNCRK": "FLORENCE CREEK",
    "FULTNAV": "FULTON AVENUE",
    "GLDNGT": "GOLDEN GATE",
    "HALFMN": "HALF MOON",
    "HGHTSTN": "HIGHSTOWN",
    "KRNCNYN": "KERN CANYON",
    "LSBANOS": "LOS BANOS",
    "MTDIABLO": "MT DIABLO",
    "MTNVIEW": "MOUNTAIN VIEW",
    "PLSNTHL": "PLEASANT HILL",
    "PTREYES": "POINT REYES",
    "RIDGCST": "RIDGE CREST",
    "SNBRUNO": "SAN BRUNO",
    "SNCARLS": "SAN CARLOS",
    "SNFRNCSC": "SAN FRANCISCO",
    "SNJUAN": "SAN JUAN",
    "SNMATEO": "SAN MATEO",
    "SRRAMNT": "SACRAMENTO",
    "TMPLTCTY": "TEMPLE CITY",
    "TRCYLND": "TRACY LANDING",
    "WESTPNT": "WEST POINT",
    "WESTSIDE": "WEST SIDE",
    "WILLMTT": "WILLAMETTE",
}


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two points in km."""
    R = 6371.0
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return R * 2 * atan2(sqrt(a), sqrt(1 - a))


def _extract_pnode_prefix(pnode_name: str) -> str:
    """Extract substation prefix from a CAISO PNode name.

    Examples:
        ARCATA_6_N001 -> ARCATA
        2C577C1_7_N001 -> 2C577C1
        BULLARD_1_B1 -> BULLARD
    """
    parts = pnode_name.split("_")
    return parts[0].upper().strip() if parts else pnode_name.upper().strip()


def _clean_grip_name(name: str) -> str:
    """Clean a GRIP substation name for matching."""
    return re.sub(r"\s+", " ", name.strip().upper())


def match_pnodes_to_grip(
    pnode_names: list[str],
    grip_df: pd.DataFrame,
    pnode_coords: dict = None,
    cache_path: Path = None,
    force: bool = False,
    max_distance_km: float = 50.0,
) -> pd.DataFrame:
    """
    Match PNode names to GRIP substations using name matching + proximity fallback.

    Args:
        pnode_names: List of CAISO PNode names (e.g. "ARCATA_6_N001")
        grip_df: GRIP substation DataFrame (must have sub_clean, lat, lon columns)
        pnode_coords: {pnode_name: {lat, lon, ...}} from geocoder cache
        cache_path: Optional path to cache matches CSV
        force: Re-compute even if cache exists
        max_distance_km: Max distance for proximity matching

    Returns:
        DataFrame with columns: caiso_prefix, grip_substation, division,
        lat, lon, match_type, match_score, distance_km, pnode_names
    """
    if cache_path and cache_path.exists() and not force:
        logger.info(f"Loading cached PNode-GRIP matches from {cache_path}")
        return pd.read_csv(cache_path)

    # Build prefix -> pnode_names mapping
    prefix_to_pnodes = {}
    for pname in pnode_names:
        prefix = _extract_pnode_prefix(pname)
        prefix_to_pnodes.setdefault(prefix, []).append(pname)

    # Build GRIP substation lookup: clean_name -> {division, lat, lon, ...}
    grip_subs = {}
    for _, row in grip_df.drop_duplicates(subset=["sub_clean"]).iterrows():
        clean = row["sub_clean"]
        if not clean:
            continue
        grip_subs[clean] = {
            "division": row.get("division", ""),
            "lat": row.get("lat"),
            "lon": row.get("lon"),
        }

    # Build override lookup: pnode_prefix -> grip_name
    override_lookup = {k.upper(): v.upper() for k, v in NAME_OVERRIDES.items()}

    matches = []
    matched_prefixes = set()
    matched_grip_subs = set()

    # ── Pass 1: Exact name matching ──
    for prefix, pnames in prefix_to_pnodes.items():
        # Try direct match
        target = override_lookup.get(prefix, prefix)
        if target in grip_subs:
            info = grip_subs[target]
            matches.append({
                "caiso_prefix": prefix,
                "grip_substation": target,
                "division": info["division"],
                "lat": info["lat"],
                "lon": info["lon"],
                "match_type": "name",
                "match_score": 1.0,
                "distance_km": 0.0,
                "pnode_names": ";".join(pnames),
            })
            matched_prefixes.add(prefix)
            matched_grip_subs.add(target)

    logger.info(
        f"Pass 1 (name): {len(matched_prefixes)}/{len(prefix_to_pnodes)} "
        f"prefixes matched to GRIP substations"
    )

    # ── Pass 2: Geographic proximity fallback ──
    if pnode_coords:
        # Build coordinates for name-matched PNodes (inherit GRIP substation coords)
        pnode_latlons = {}
        for m in matches:
            if m["lat"] is not None and m["lon"] is not None:
                for pname in m["pnode_names"].split(";"):
                    pnode_latlons[pname] = (m["lat"], m["lon"])

        # Add coordinates from geocoder cache for remaining PNodes
        for pname in pnode_names:
            if pname not in pnode_latlons and pname in pnode_coords:
                coord = pnode_coords[pname]
                lat = coord.get("lat")
                lon = coord.get("lon")
                if lat is not None and lon is not None:
                    pnode_latlons[pname] = (lat, lon)

        # For each unmatched GRIP substation, find nearest PNode
        unmatched_grip = {
            name: info for name, info in grip_subs.items()
            if name not in matched_grip_subs
        }

        proximity_matches = 0
        for grip_name, grip_info in unmatched_grip.items():
            grip_lat = grip_info.get("lat")
            grip_lon = grip_info.get("lon")
            if grip_lat is None or grip_lon is None:
                continue

            best_pnode = None
            best_dist = float("inf")

            for pname, (plat, plon) in pnode_latlons.items():
                dist = haversine_km(grip_lat, grip_lon, plat, plon)
                if dist < best_dist:
                    best_dist = dist
                    best_pnode = pname

            if best_pnode and best_dist <= max_distance_km:
                prefix = _extract_pnode_prefix(best_pnode)
                score = max(0.0, 1.0 - best_dist / max_distance_km)
                matches.append({
                    "caiso_prefix": prefix,
                    "grip_substation": grip_name,
                    "division": grip_info["division"],
                    "lat": grip_lat,
                    "lon": grip_lon,
                    "match_type": "proximity",
                    "match_score": round(score, 4),
                    "distance_km": round(best_dist, 2),
                    "pnode_names": best_pnode,
                })
                proximity_matches += 1

        logger.info(
            f"Pass 2 (proximity): {proximity_matches} GRIP substations "
            f"matched to nearest PNode (max {max_distance_km}km)"
        )

    result_df = pd.DataFrame(matches)
    logger.info(
        f"Total matches: {len(result_df)} "
        f"(name: {len([m for m in matches if m['match_type'] == 'name'])}, "
        f"proximity: {len([m for m in matches if m['match_type'] == 'proximity'])})"
    )

    if cache_path:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        result_df.to_csv(cache_path, index=False)
        logger.info(f"Cached matches to {cache_path}")

    return result_df
