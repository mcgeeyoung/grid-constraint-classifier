"""NYISO settlement-point name normalizer + curated centroids.

NYISO publishes 11 load zones (PTID 4001-4011 ish) plus ~700 generator
buses. The driver's `list_load_nodes` returns the 11 zones; gen pnodes
are accessed via `fetch_da_hourly_buses`.

Zone centroids hand-curated to the canonical city per zone.
"""
from __future__ import annotations

# Map by canonical NYISO name (matches what driver emits as pnode_name).
NYISO_ZONE_CENTROIDS: dict[str, tuple[float, float]] = {
    "WEST":    (42.8864, -78.8784),  # Buffalo
    "GENESE":  (43.1566, -77.6088),  # Rochester
    "CENTRL":  (43.0481, -76.1474),  # Syracuse
    "NORTH":   (44.6995, -74.5230),  # Massena / North Country
    "MHK VL":  (43.1009, -75.2327),  # Utica / Mohawk Valley
    "CAPITL":  (42.6526, -73.7562),  # Albany / Capital District
    "HUD VL":  (41.7004, -73.9209),  # Poughkeepsie / Hudson Valley
    "MILLWD":  (41.2090, -73.7287),  # Millwood
    "DUNWOD":  (40.9854, -73.8693),  # Yonkers / Lower Hudson
    "N.Y.C.":  (40.7128, -74.0060),  # New York City (Zone J)
    "LONGIL":  (40.7891, -73.1350),  # Hauppauge / Long Island
}

# Driver also returns these under a few PTID synonyms; expose the same
# coords keyed by PTID so HIFLD-style consumers and the asset map can
# look up by either pnode_id or pnode_name.
NYISO_PTID_TO_ZONE: dict[str, str] = {
    "61752": "WEST",
    "61753": "GENESE",
    "61754": "CENTRL",
    "61755": "NORTH",
    "61756": "MHK VL",
    "61757": "CAPITL",
    "61758": "HUD VL",
    "61759": "MILLWD",
    "61760": "DUNWOD",
    "61761": "N.Y.C.",
    "61762": "LONGIL",
}


def aggregate_centroids() -> dict[str, tuple[float, float]]:
    """Return centroids keyed by both PTID and name (driver emits PTID as pnode_id)."""
    out: dict[str, tuple[float, float]] = {}
    for name, latlon in NYISO_ZONE_CENTROIDS.items():
        out[name] = latlon
    for ptid, name in NYISO_PTID_TO_ZONE.items():
        if name in NYISO_ZONE_CENTROIDS:
            out[ptid] = NYISO_ZONE_CENTROIDS[name]
    return out


def normalize_pnode_name(pname: str) -> list[str]:
    """Stub normalizer -- NYISO load zones are fully covered by centroids;
    gen pnodes (rare ingestion target for asset mapping) are best left
    to manual curation per project."""
    return []
