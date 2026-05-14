"""ERCOT settlement-point name normalizer for HIFLD matching.

ERCOT pnode naming surveyed against DAM 2026-04-18 (1,096 SPs):

| Prefix    | Type           | Match strategy |
|-----------|----------------|----------------|
| `LZ_*`    | Load Zone      | Hand-curated centroids (ERCOT_ZONE_CENTROIDS). Cities/regions, not substations. |
| `HB_*`    | Hub            | Hand-curated centroids (ERCOT_HUB_CENTROIDS). Same reasoning. |
| `DC_*`    | DC tie         | Hand-curated (ERCOT_DC_TIES). Single coordinate per tie. |
| (other)   | Resource Node  | HIFLD substation name match via `normalize_resource_node_name`. |

Resource-node names tend to follow `<NUM><NAME>_<UNIT>_RN` or
`<NAME>_<UNIT>` patterns; the normalizer strips leading digits, the
trailing `_RN` / unit suffix, and routes to the shared HIFLD
normalizer.
"""
from __future__ import annotations

import re

from isos.coords.hifld import normalize


# Hand-curated zone centroids (rough city/region anchors -- not substations).
ERCOT_ZONE_CENTROIDS: dict[str, tuple[float, float]] = {
    "LZ_HOUSTON":   (29.7604, -95.3698),  # Houston
    "LZ_NORTH":     (32.7767, -96.7970),  # Dallas
    "LZ_SOUTH":     (28.8053, -97.3964),  # roughly San Antonio / Cuero (south zone)
    "LZ_WEST":      (32.4487, -99.7331),  # Abilene (west zone center)
    "LZ_AEN":       (30.2672, -97.7431),  # Austin Energy
    "LZ_CPS":       (29.4241, -98.4936),  # CPS Energy / San Antonio
    "LZ_LCRA":      (30.5083, -97.8281),  # Lower Colorado River Authority (Round Rock area)
    "LZ_RAYBN":     (33.6692, -96.0911),  # Rayburn Country EC, Rockwall TX
}

ERCOT_HUB_CENTROIDS: dict[str, tuple[float, float]] = {
    "HB_HOUSTON":   (29.7604, -95.3698),
    "HB_NORTH":     (32.7767, -96.7970),
    "HB_SOUTH":     (29.4241, -98.4936),  # San Antonio
    "HB_WEST":      (32.4487, -99.7331),  # Abilene
    "HB_PAN":       (35.2220, -101.8313),  # Amarillo / Panhandle
    "HB_HUBAVG":    (31.2504, -98.0000),  # Geographic centroid of TX
    "HB_BUSAVG":    (31.2504, -98.0000),
}

# DC ties: rough lat/lon at the actual interconnection point.
ERCOT_DC_TIES: dict[str, tuple[float, float]] = {
    "DC_E":    (33.4734, -94.0353),  # East tie at Monticello / NE Texas
    "DC_L":    (27.5306, -99.4803),  # Eagle Pass / Laredo
    "DC_N":    (33.7676, -100.5879),  # North tie / Oklaunion
    "DC_R":    (28.7000, -100.5000),  # Railroad DC tie / Eagle Pass area
}


def aggregate_centroids() -> dict[str, tuple[float, float]]:
    """Combined zone + hub + DC-tie hand-curated coords."""
    out: dict[str, tuple[float, float]] = {}
    out.update(ERCOT_ZONE_CENTROIDS)
    out.update(ERCOT_HUB_CENTROIDS)
    out.update(ERCOT_DC_TIES)
    return out


_SUFFIX_PATTERN = re.compile(
    r"^(ALL|RN|UN\d*|U\d+|G\d+|GR\d+|GT\d+|ST\d+|CT\d+|DG\d+|DGR\d*|"
    r"BES\d*|BTC\d*|ESS\d*|BAT\d*|PV\d*|SOL\d*|SOLAR\d*|LD\d*|"
    r"WD\d*|WIND\d*|GEN\d*|UNIT\d*|U|G|GT|ST|CT)$"
)

_MIN_TOKEN_LEN = 4


def normalize_resource_node_name(pname: str) -> list[str]:
    """Extract substation-name candidates from an ERCOT resource node name.

    Returns a list of candidate normalized strings to try in order
    (most-specific first). Empty list to skip.

    Examples:
      `7RNCHSLR_ALL`        -> ["RNCHSLR"]
      `BRP_BTC1_UNIT1`      -> ["BRPBTC", "BRP"]
      `BARNEY_M_BES1`       -> ["BARNEYM", "BARNEY"]
      `LON_HILLS_REC_UN1`   -> ["LONHILLSREC", "LONHILLS", "LON"]
      `WHITTIER_BES1`       -> ["WHITTIER"]
      `DOW_G37_G35`         -> []   (only "DOW" survives -- too generic, dropped)

    `LZ_*`, `HB_*`, `DC_*` prefixes return [] -- the caller routes those
    through hand-curated centroids instead of HIFLD.
    """
    if not pname:
        return []
    p = str(pname).strip().upper()
    if p.startswith(("LZ_", "HB_", "DC_")):
        return []

    # Drop a leading single-digit number on the first token.
    p = re.sub(r"^(\d+)([A-Z])", r"\2", p)

    # Tokenize on `_`, drop trailing unit/type suffixes.
    parts = p.split("_")
    while len(parts) > 1 and _SUFFIX_PATTERN.match(parts[-1]):
        parts.pop()

    if not parts:
        return []

    # Build candidate list: longest joined first, then progressively shorter.
    # Reject candidates shorter than _MIN_TOKEN_LEN (avoids garbage matches
    # on 2-3 char abbreviations like "DOW", "AE", "U2").
    candidates: list[str] = []
    for n in range(len(parts), 0, -1):
        cand = normalize("_".join(parts[:n]))
        if len(cand) >= _MIN_TOKEN_LEN and cand not in candidates:
            candidates.append(cand)
    return candidates
