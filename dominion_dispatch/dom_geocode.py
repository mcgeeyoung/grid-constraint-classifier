"""
Geocode PJM pricing-node names within the DOM footprint (Virginia) for map placement.

Uses the same Nominatim helper as ``src.data_acquisition``; callers must rate-limit
batch calls (~1 req/s) per OSM policy.
"""

from __future__ import annotations

import logging
from typing import Optional

import requests

from src.data_acquisition import ZONE_STATE_MAP, _clean_pnode_name, _geocode_single

logger = logging.getLogger(__name__)


def geocode_pnode_name_for_dom_program(
    pnode_name: str,
    *,
    session: Optional[requests.Session] = None,
) -> Optional[tuple[float, float, str]]:
    """
    Return ``(lat, lon, matched_name)`` for a PJM bus / node name, or None.

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
