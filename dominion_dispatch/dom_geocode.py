"""
Geocode PJM pricing-node names within the DOM footprint (Virginia) for map placement.

Uses Nominatim (OpenStreetMap). Callers must rate-limit batch calls
(~1 req/s) per OSM usage policy.
"""

from __future__ import annotations

import logging
import re
from typing import Optional

import requests

logger = logging.getLogger(__name__)

# PJM zone → home-state for Nominatim search context. Originally lived
# alongside the PJM zone-LMP pipeline in src/data_acquisition.py; inlined
# here when the old src/ tree was retired in favour of wcgrid.
ZONE_STATE_MAP: dict[str, str] = {
    "AECO": "NJ", "COMED": "IL", "DOM": "VA", "DPL": "DE", "JCPL": "NJ",
    "OVEC": "OH", "PECO": "PA", "PEPCO": "MD", "PPL": "PA", "PSEG": "NJ",
    "RECO": "NJ", "AEP": "OH", "APS": "PA", "ATSI": "OH", "BGE": "MD",
    "DAY": "OH", "DEOK": "OH", "DUQ": "PA", "EKPC": "KY", "METED": "PA",
    "PENELEC": "PA", "PE": "PA",
}


def _clean_pnode_name(name: str) -> str:
    """Strip trailing digits (CHESTER4 → CHESTER) and leading number
    prefixes ("72 GOOSE" → "GOOSE", "958_HOGR" → "HOGR")."""
    cleaned = name.strip()
    cleaned = re.sub(r"^\d+[\s_]+", "", cleaned)
    cleaned = re.sub(r"\d+$", "", cleaned)
    cleaned = cleaned.strip("_ ")
    if len(cleaned) < 2:
        return name.strip()
    return cleaned


def _geocode_single(name: str, state: str, session: requests.Session) -> Optional[dict]:
    """Geocode a single pnode name via Nominatim. Returns ``{lat, lon, matched_name}`` or None."""
    query = f"{name}, {state}, USA"
    url = "https://nominatim.openstreetmap.org/search"
    params = {"q": query, "format": "json", "limit": 1, "countrycodes": "us"}
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
    except Exception as exc:
        logger.debug("Geocode failed for %r: %s", query, exc)
    return None


def geocode_pnode_name_for_dom_program(
    pnode_name: str,
    *,
    session: Optional[requests.Session] = None,
) -> Optional[tuple[float, float, str]]:
    """Return ``(lat, lon, matched_name)`` for a PJM bus / node name, or None.

    Uses the DOM zone state (**VA**) for the Nominatim query context.
    """
    if not pnode_name or not str(pnode_name).strip():
        return None
    sess = session or requests.Session()
    state = ZONE_STATE_MAP.get("DOM", "VA")
    cleaned = _clean_pnode_name(str(pnode_name))
    hit = _geocode_single(cleaned, state, sess)
    if not hit:
        return None
    return hit["lat"], hit["lon"], str(hit.get("matched_name", ""))
