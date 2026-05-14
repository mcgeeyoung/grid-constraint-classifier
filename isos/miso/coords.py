"""MISO settlement-point name normalizer + curated hub centroids.

MISO loadzone names: `<BA_PREFIX>.<SUBZONE>`, e.g. `AECI.ALTW`,
`CONS.BECO`, `WEC.WPSI`. Hubs: `MICHIGAN.HUB`, `INDIANA.HUB`,
`MINN.HUB`, etc.

For zone aggregates we hand-curate hub centroids. For node-level
matching we try the suffix token (after the dot) against HIFLD; MISO
covers many states (MN/WI/IA/IL/MO/IN/MI/AR/MS/LA), so caller should
pass `states=()` (empty) or a wide list.
"""
from __future__ import annotations

import re

from isos.coords.hifld import normalize


MISO_HUB_CENTROIDS: dict[str, tuple[float, float]] = {
    "MICHIGAN.HUB":   (43.0000, -84.5000),  # Lower Michigan center
    "INDIANA.HUB":    (40.0000, -86.0000),  # Central Indiana
    "ILLINOIS.HUB":   (40.0000, -89.0000),  # Central Illinois
    "MINN.HUB":       (45.0000, -93.5000),  # Minneapolis-St Paul
    "ARKANSAS.HUB":   (34.7500, -92.2500),  # Little Rock
    "LOUISIANA.HUB":  (30.4500, -91.1500),  # Baton Rouge
    "MISSISSIPPI.HUB": (32.3000, -90.2000), # Jackson MS
    "TEXAS.HUB":      (32.5000, -94.0000),  # MISO South / E Texas
}

# Loadzone city/region anchors for the most-cited BAs.
MISO_LOADZONE_CENTROIDS: dict[str, tuple[float, float]] = {
    "AECI.ALTW":  (38.6270, -90.1994),  # Ameren Missouri / St. Louis
    "AECI.AMMO":  (38.5000, -94.5000),  # Associated Electric Coop, MO
    "AECI.CWLD":  (37.0000, -93.0000),  # AECI / Springfield MO
    "CONS.BECO":  (43.0000, -84.5000),  # Consumers Energy
    "DEMI.AMMO":  (42.3314, -83.0458),  # DTE Detroit
    "DECO.AMMO":  (42.3314, -83.0458),  # DTE / Detroit Edison
    "EAI.EAI":    (34.7500, -92.2500),  # Entergy Arkansas
    "ELL.ELL":    (30.4500, -91.1500),  # Entergy Louisiana
    "EES.EES":    (32.3000, -90.2000),  # Entergy Mississippi
    "ETX.ETX":    (32.5000, -94.0000),  # Entergy Texas
    "MEC.MEC":    (41.5868, -93.6250),  # MidAmerican Energy / Des Moines
    "NSP.NSP":    (45.0000, -93.5000),  # Xcel Northern States Power
    "WEC.WEC":    (43.0389, -87.9065),  # WE Energies / Milwaukee
}


def aggregate_centroids() -> dict[str, tuple[float, float]]:
    out: dict[str, tuple[float, float]] = {}
    out.update(MISO_HUB_CENTROIDS)
    out.update(MISO_LOADZONE_CENTROIDS)
    return out


_TRAILING_DIGITS_RE = re.compile(r"\d+$")
_TRAILING_UNIT_RE = re.compile(
    r"_?(GT\d*|ST\d*|CT\d*|U\d+|UN\d*|G\d+|GR\d+|BES\d*|BAT\d*|ESS\d*|"
    r"PV\d*|SOL\d*|WIND\d*|WND\d*|CC\d*|UNIT\d*|MP|FSE|ALL|AUX\d*|AGG|AZ|RES)$"
)


def normalize_pnode_name(pname: str) -> list[str]:
    """Extract substation/project candidates from a MISO node name.

    MISO patterns:
      `AECI.ALTW`         -> ["ALTW"]
      `AMMO.KEOKUK5`      -> ["KEOKUK5", "KEOKUK"]
      `NSP.WHEATON_13`    -> ["WHEATON", "WHEATON13"]
      `CONS.LUDINGTN2`    -> ["LUDINGTN"]
      `MEC.BEPM.CPZD`     -> ["CPZD", "BEPM"]
      `WEC.PORTWA1CT1`    -> ["PORTWA"] (trailing CT1 unit suffix stripped)
      `INDIANA.HUB`       -> []   (handled by centroid)
    """
    if not pname:
        return []
    p = str(pname).strip().upper()

    if "HUB" in p:
        return []

    # Strip _GT1 / _BES1 / etc. suffix tokens.
    p_clean = _TRAILING_UNIT_RE.sub("", p)

    parts = [t for t in re.split(r"[._]", p_clean) if t]
    if not parts:
        return []
    nondigit = [t for t in parts if not t.isdigit()]
    if not nondigit:
        return []

    # Drop leading BAA token when there are >= 2 meaningful tokens.
    if len(nondigit) >= 2:
        candidates_pool = nondigit[1:]
    else:
        candidates_pool = nondigit

    candidates: list[str] = []

    def _add(c: str) -> None:
        if c and len(c) >= 4 and c not in candidates:
            candidates.append(c)

    # Try last token first (most likely the substation), then second-to-last.
    for tok in reversed(candidates_pool):
        n = normalize(tok)
        _add(n)
        n_stripped = _TRAILING_DIGITS_RE.sub("", n) or n
        if n_stripped != n:
            _add(n_stripped)

    # Also try the joined pool (handles `WHEATON_13` -> `WHEATON13`).
    if len(candidates_pool) >= 2:
        _add(normalize("_".join(candidates_pool)))

    return candidates[:6]
