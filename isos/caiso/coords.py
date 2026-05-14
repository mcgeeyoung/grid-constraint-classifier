"""CAISO APnode/PNode name normalizer + curated centroids.

CAISO names:

  `DLAP_<UTILITY>-APND`     default LAP per utility (PG&E, SCE, SDG&E, VEA)
  `<X>_<Y>-APND`            sub-LAPs (SLAPs)
  `TH_<HUB>_GEN[_OFFPEAK]`  trading hubs (NP15, ZP26, SP15)
  `<NAME>_<NUM>_N<NUM>`     bus-level pricing nodes (METCALF_1_N018)
  `DGAP_<BAA>-APND`         WECC external BAAs (handled by isos/wecc/)

For aggregates (DLAP/SLAP/TH) the centroid is the answer; bus-level
pnodes can be HIFLD-matched in CA.
"""
from __future__ import annotations

import re

from isos.coords.hifld import normalize


# DLAPs and the major SLAPs.
CAISO_DLAP_CENTROIDS: dict[str, tuple[float, float]] = {
    "DLAP_PGAE-APND":    (37.7749, -122.4194),  # PG&E / San Francisco
    "DLAP_SCE-APND":     (34.0522, -118.2437),  # SCE / Los Angeles
    "DLAP_SDGE-APND":    (32.7157, -117.1611),  # SDG&E / San Diego
    "DLAP_VEA-APND":     (35.7700, -114.8500),  # Valley Electric / Pahrump NV
    # Sub-LAPs (rough city anchors)
    "SLAP_PGCC-APND":    (38.5816, -121.4944),  # PGCC / Sacramento
    "SLAP_PGEB-APND":    (37.8044, -122.2712),  # PGEB / East Bay (Oakland)
    "SLAP_PGF1-APND":    (36.7378, -119.7871),  # PGF1 / Fresno
    "SLAP_PGFG-APND":    (37.7749, -122.4194),  # PGFG / SF
    "SLAP_PGNB-APND":    (38.4404, -122.7141),  # PGNB / North Bay (Santa Rosa)
    "SLAP_PGNP-APND":    (40.5865, -122.3917),  # PGNP / North Coast (Redding)
    "SLAP_PGSA-APND":    (37.5630, -122.3255),  # PGSA / San Mateo / SF Peninsula
    "SLAP_PGSB-APND":    (37.3382, -121.8863),  # PGSB / South Bay (San Jose)
    "SLAP_PGSF-APND":    (37.7749, -122.4194),  # PGSF / SF City
    "SLAP_PGST-APND":    (38.5816, -121.4944),  # PGST / Stockton/Central
    "SLAP_PGZP-APND":    (37.7749, -122.4194),  # PGZP / SF
    "SLAP_SCEC-APND":    (33.6846, -117.8265),  # SCEC / Coastal SCE (Irvine)
    "SLAP_SCEN-APND":    (34.4208, -119.6982),  # SCEN / North SCE (Santa Barbara)
    "SLAP_SCEW-APND":    (34.0522, -118.2437),  # SCEW / West LA
    "SLAP_SCNW-APND":    (35.3733, -119.0187),  # SCNW / North West (Bakersfield)
    "SLAP_SCHD-APND":    (33.7701, -118.1937),  # SCHD / Long Beach (high-density)
    "SLAP_SDG1-APND":    (32.7157, -117.1611),  # SDG&E sub-1
}

# Trading hubs (zonal averages).
CAISO_HUB_CENTROIDS: dict[str, tuple[float, float]] = {
    "TH_NP15_GEN-APND":         (37.7749, -122.4194),  # NP15 / North of Path 15 (SF)
    "TH_NP15_GEN_ONPEAK-APND":  (37.7749, -122.4194),
    "TH_NP15_GEN_OFFPEAK-APND": (37.7749, -122.4194),
    "TH_SP15_GEN-APND":         (34.0522, -118.2437),  # SP15 / South of Path 15 (LA)
    "TH_SP15_GEN_ONPEAK-APND":  (34.0522, -118.2437),
    "TH_SP15_GEN_OFFPEAK-APND": (34.0522, -118.2437),
    "TH_ZP26_GEN-APND":         (35.3733, -119.0187),  # ZP26 / Zone of Path 26 (Bakersfield)
    "TH_ZP26_GEN_ONPEAK-APND":  (35.3733, -119.0187),
    "TH_ZP26_GEN_OFFPEAK-APND": (35.3733, -119.0187),
}


def aggregate_centroids() -> dict[str, tuple[float, float]]:
    out: dict[str, tuple[float, float]] = {}
    out.update(CAISO_DLAP_CENTROIDS)
    out.update(CAISO_HUB_CENTROIDS)
    return out


_BUS_NODE_RE = re.compile(r"^([A-Z][A-Z0-9]{2,})_\d+_(N|B)\d+$")


def normalize_pnode_name(pname: str) -> list[str]:
    """Try to extract a substation token from CAISO bus-level pnode names.

    Examples:
      `METCALF_1_N018`  -> ["METCALF"]
      `MISSION_6_N001`  -> ["MISSION"]
      `OAKLND3_7_N001`  -> ["OAKLND"]
      `BELMONT_1_N001`  -> ["BELMONT"]

    Aggregates (DLAP_/SLAP_/TH_/DGAP_) return [] -- those are handled by
    centroids (DLAP/SLAP/TH) or by isos/wecc (DGAP).
    """
    if not pname:
        return []
    p = str(pname).strip().upper()
    if p.startswith(("DLAP_", "SLAP_", "TH_", "DGAP_")) or p.endswith("-APND") and any(
        p.startswith(prefix) for prefix in ("DLAP_", "SLAP_", "TH_", "DGAP_")
    ):
        return []

    # Bus-level: NAME_<NUM>_N<NUM> or NAME_<NUM>_B<NUM>.
    name_only = p[:-5] if p.endswith("-APND") else p
    m = _BUS_NODE_RE.match(name_only)
    if m:
        # Strip trailing single digit on the substation name (OAKLND3 -> OAKLND).
        sub = re.sub(r"\d+$", "", m.group(1)) or m.group(1)
        n = normalize(sub)
        return [n] if len(n) >= 4 else []
    return []
