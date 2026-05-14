"""ISO-NE settlement-point name normalizer + curated centroids.

ISO-NE pnodes:

  `.Z.<ZONE>`           load zones (8) -- city/region centroids
  `.H.INTERNAL_HUB`     internal hub
  `.I.<X>`              interface (external)
  `UN.<...>`            unit network nodes (cryptic codes; very hard to match)
  generic plant codes   the long tail

For LZ/HUB the hand-curated centroids are the answer. Network-node
HIFLD matching expectation is low: ISO-NE codes look like
`UN.FRNKLNSQ13.810CC` -- "FRNKLNSQ" is "Franklin Square" but split
across dotted tokens with embedded voltage and circuit IDs.
"""
from __future__ import annotations

import re

from isos.coords.hifld import normalize


# ISO-NE load zone city centroids (rough -- pick the largest population
# center inside each zone or the BA control center).
ISONE_ZONE_CENTROIDS: dict[str, tuple[float, float]] = {
    ".Z.MAINE":         (44.3106, -69.7795),  # Augusta ME
    ".Z.NEWHAMPSHIRE":  (43.2081, -71.5376),  # Concord NH
    ".Z.VERMONT":       (44.2601, -72.5754),  # Montpelier VT
    ".Z.CONNECTICUT":   (41.7658, -72.6734),  # Hartford CT
    ".Z.RHODEISLAND":   (41.8240, -71.4128),  # Providence RI
    ".Z.SEMASS":        (41.7003, -71.1559),  # Fall River / SE Mass
    ".Z.WCMASS":        (42.2626, -71.8023),  # Worcester / W Central Mass
    ".Z.NEMASSBOST":    (42.3601, -71.0589),  # Boston
}

ISONE_HUB_CENTROIDS: dict[str, tuple[float, float]] = {
    ".H.INTERNAL_HUB":  (42.3470, -71.5500),  # ISO-NE control center, Holyoke MA region
}


def aggregate_centroids() -> dict[str, tuple[float, float]]:
    out: dict[str, tuple[float, float]] = {}
    out.update(ISONE_ZONE_CENTROIDS)
    out.update(ISONE_HUB_CENTROIDS)
    return out


_TOKEN_VOLTAGE_RE = re.compile(r"^([A-Z]+?)(\d+)?$")


def normalize_pnode_name(pname: str) -> list[str]:
    """Best-effort normalizer for ISO-NE pnodes that aren't in the curated set.

    Empty for `.Z.*` / `.H.*` / `.I.*` (handled by centroids or skipped).
    For `UN.<token>13.<circuit>` style -- try the middle dotted token
    with trailing digits stripped.

    Match expectation is low; this is best-effort scaffolding.
    """
    if not pname:
        return []
    p = str(pname).strip().upper()
    if p.startswith((".Z.", ".H.", ".I.")):
        return []

    parts = [t for t in p.split(".") if t]
    candidates: list[str] = []
    for tok in parts:
        m = _TOKEN_VOLTAGE_RE.match(tok)
        if m and len(m.group(1)) >= 5:
            candidates.append(normalize(m.group(1)))
    # Dedupe preserving order.
    seen: set[str] = set()
    out: list[str] = []
    for c in candidates:
        if c and c not in seen:
            seen.add(c)
            out.append(c)
    return out
