"""SPP settlement-point name normalizer + curated centroids.

SPP names:

  `SPPNORTH_HUB` / `SPPSOUTH_HUB`  -- system hubs
  `<BAA>HUB...`                     -- entity sub-hubs
  `<BAA>.<NAME>` or `<BAA>_<NAME>` -- per-entity SLs

For SLs the suffix token is often the substation name. SPP spans
KS/MO/OK/AR/TX/NM/NE/SD/ND/MT, so HIFLD lookup uses a wide states list.
"""
from __future__ import annotations

import re

from isos.coords.hifld import normalize


SPP_HUB_CENTROIDS: dict[str, tuple[float, float]] = {
    "SPPNORTH_HUB":  (39.0997, -94.5786),  # Kansas City
    "SPPSOUTH_HUB":  (35.4676, -97.5164),  # Oklahoma City
}

# Entity hub centroids -- city/region anchors.
SPP_ENTITY_HUB_CENTROIDS: dict[str, tuple[float, float]] = {
    "KCPLHUB":          (39.0997, -94.5786),  # KCP&L / Kansas City
    "WRHUB24":          (38.0000, -97.0000),  # Westar / central KS
    "SPS_WFEC_HUB25":   (35.4676, -97.5164),  # SPS / WFEC OK
    "OMPA_GENHUB":      (35.4676, -97.5164),  # OMPA Oklahoma
    "GRDA_HUB":         (36.4000, -94.9000),  # GRDA / Grand River OK
    "EDEP_SWMPEPHUB":   (37.0000, -94.5000),  # Empire District
    "ETEC_HUB":         (35.4676, -97.5164),  # East Texas Electric Coop
    "CSWS_HUB":         (33.4500, -94.0500),  # AEP-SWEPCO
    "SECI_HUB":         (35.0000, -94.5000),  # Sunflower Electric KS
    "LES_HUB":          (40.8136, -96.7026),  # Lincoln Electric NE
    "NPPD2017HUB":      (41.4000, -99.0000),  # Nebraska Public Power
    "LAP_HUB":          (35.7000, -94.0000),  # Louisiana area
    "GSEC_HUB":         (32.0000, -97.0000),  # Golden Spread / TX
    "HAST_TNSK_HUB":    (40.5853, -98.3839),  # Hastings NE / TriState
    "MEAI_CRG_HUB":     (40.0000, -100.5000), # MEAI / Cargill region
    "TSPM_SOURCEHUB":   (33.5779, -101.8552), # SPS source hub / Lubbock
    "SWPW_HUB":         (33.0000, -103.5000), # Southwestern Public Service NM
    "UCUHUB":           (37.0000, -100.0000), # Upland Coop Utility
}


def aggregate_centroids() -> dict[str, tuple[float, float]]:
    out: dict[str, tuple[float, float]] = {}
    out.update(SPP_HUB_CENTROIDS)
    out.update(SPP_ENTITY_HUB_CENTROIDS)
    return out


_SKIP_TOKENS = {"VOLT", "AUX", "AUX1", "AUX2", "MTR", "METER", "TIE", "GEN"}
_TRAILING_DIGITS_RE = re.compile(r"\d+$")
_TRAILING_UNIT_RE = re.compile(
    r"_?(GT\d*|ST\d*|CT\d*|U\d+|UN\d*|G\d+|GR\d+|BES\d*|BAT\d*|ESS\d*|"
    r"PV\d*|SOL\d*|WIND\d*|WND\d*|CC\d*|UNIT\d*|MP|MSR|FSE|ALL|AUX\d*)$"
)


def normalize_pnode_name(pname: str) -> list[str]:
    """Extract substation/project candidates from an SPP settlement-location name.

    SPP SL naming has multiple shapes:
      `KCPL.HAW10`               -> ["HAW10", "HAW"]
      `KCPL.PRQUEEN`             -> ["PRQUEEN"]
      `KCPL.SLATECREEK`          -> ["SLATECREEK"]
      `WR_HOLCOMB`               -> ["HOLCOMB"]
      `WAUE.BEPM.WILTON1`        -> ["WILTON1", "WILTON", "BEPMWILTON1"]
      `WACM.LAP.FREMONTCANYON`   -> ["FREMONTCANYON"]
      `EDE.NORTHFORK`            -> ["NORTHFORK"]
      `WR.MIDW.SMOKY1.ENEL`      -> ["ENEL", "SMOKY1", "SMOKY"]
      `SPPSOUTH_HUB`             -> []   (handled by centroid)
      `KCPL.VOLT.0269`           -> []   (VOLT meter codes -- skipped)

    Strategy:
      1. Reject hub-tagged names and `*.VOLT.*` meter codes.
      2. Tokenize on `.` and `_`.
      3. Drop the leading BAA token (or the leading two if both look like
         BAA-style 3-5 char codes).
      4. Try the **last** non-suffix token first (most likely substation),
         then the second-to-last, then the joined form.
      5. Strip trailing unit suffixes (`_GT1`, `_BES1`, `_ALL`, etc.).
      6. Strip trailing digits as a fallback variant.
    """
    if not pname:
        return []
    p = str(pname).strip().upper()

    # Skip hubs (handled by centroid map).
    if "HUB" in p:
        return []

    # Drop _GT1 / _BES1 / etc. suffix tokens.
    p_clean = _TRAILING_UNIT_RE.sub("", p)

    parts = [t for t in re.split(r"[._]", p_clean) if t]
    if not parts:
        return []

    # Skip pure-digit tokens (KCPL.VOLT.0269) -- the meaningful token is VOLT,
    # which is itself a meter-code marker. Reject if any token is in skip set
    # AND it's the only meaningful name token.
    nondigit = [t for t in parts if not t.isdigit()]
    meaningful = [t for t in nondigit if t not in _SKIP_TOKENS]
    if not meaningful:
        return []

    # Heuristic: drop the leading 1-2 tokens (BAA prefix(es)) when there
    # are >= 3 meaningful tokens.
    if len(meaningful) >= 3:
        candidates_pool = meaningful[1:]
    elif len(meaningful) == 2:
        candidates_pool = meaningful[1:]
    else:
        candidates_pool = meaningful

    candidates: list[str] = []

    def _add(cand: str) -> None:
        if cand and len(cand) >= 4 and cand not in candidates:
            candidates.append(cand)

    # Try the last token first (most likely the project / substation name).
    for tok in reversed(candidates_pool):
        n = normalize(tok)
        _add(n)
        # Variant with trailing digits stripped (HAW10 -> HAW).
        n_stripped = _TRAILING_DIGITS_RE.sub("", n) or n
        if n_stripped != n:
            _add(n_stripped)

    # Joined-pool form (e.g. "WAUE.BEPM.WILTON1" -> "BEPMWILTON1").
    if len(candidates_pool) >= 2:
        _add(normalize("_".join(candidates_pool)))

    return candidates[:6]
