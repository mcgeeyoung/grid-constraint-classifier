"""HIFLD Electric Substations loader.

Sources the national substations dataset (chadbraden HIFLD Substations
1_9_25 mirror, ~77,946 features). The CSV is fetched once via the
download script at `scripts/download_hifld.py` (or the equivalent
reachable from `~/claude-tmp/download_hifld.py`) and lives at
`~/claude/inputs/data/hifld/substations.csv` by default.

The loader normalizes substation names into a lookup keyed by
`(state, normalized_name)` so per-ISO matchers can join in O(1).
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

import pandas as pd

logger = logging.getLogger(__name__)

# Default location for the downloaded CSV.
def default_hifld_path() -> Path:
    return Path.home() / "claude" / "inputs" / "data" / "hifld" / "substations.csv"


# Strip non-letters/digits, drop common substation suffixes, uppercase.
_SUFFIX_TOKENS = (
    "SUBSTATION", "SUB", "SS", "STATION", "TAP", "SWITCHYARD", "SWITCH",
    "SWYRD", "PLANT", "POWER", "ELECTRIC", "LIGHT", "ENERGY",
)


def normalize(name: str) -> str:
    """Normalize a substation/pnode name for fuzzy joins.

    Strategy: uppercase, strip non-alphanumerics, drop trailing suffix
    tokens like SUBSTATION/TAP/PLANT. Returns "" for empty/garbage input.
    """
    if not name:
        return ""
    s = re.sub(r"[^A-Za-z0-9]+", " ", str(name)).strip().upper()
    if not s:
        return ""
    # Drop trailing suffix tokens (one or more).
    parts = s.split()
    while len(parts) > 1 and parts[-1] in _SUFFIX_TOKENS:
        parts.pop()
    return "".join(parts)


@dataclass(frozen=True)
class HifldRow:
    """One HIFLD substation row, projected to the fields we need."""

    name: str
    state: str
    city: str
    county: str
    lat: float
    lon: float
    max_volt: Optional[float]
    norm_name: str


class HifldLookup:
    """In-memory index of HIFLD substations.

    Build once per process; query via `find_by_name` (returns the best
    match given an optional state filter and minimum-voltage filter).
    """

    def __init__(self, rows: list[HifldRow]):
        self.rows = rows
        # Primary index: (state, norm_name) -> list[HifldRow]
        self._by_state_norm: dict[tuple[str, str], list[HifldRow]] = {}
        # Cross-state index for fallback when state isn't known.
        self._by_norm: dict[str, list[HifldRow]] = {}
        for r in rows:
            key = (r.state.upper(), r.norm_name)
            self._by_state_norm.setdefault(key, []).append(r)
            self._by_norm.setdefault(r.norm_name, []).append(r)

    @classmethod
    def from_csv(cls, path: Optional[Path] = None) -> "HifldLookup":
        """Load HIFLD substations CSV and build the index."""
        path = Path(path) if path else default_hifld_path()
        if not path.is_file():
            raise FileNotFoundError(
                f"HIFLD CSV not found at {path}. "
                f"Run scripts/download_hifld.py to fetch it."
            )
        logger.info("Loading HIFLD from %s", path)
        df = pd.read_csv(
            path,
            usecols=[
                "NAME", "STATE", "CITY", "COUNTY",
                "LATITUDE", "LONGITUDE", "MAX_VOLT", "STATUS",
            ],
            dtype={"NAME": str, "STATE": str, "CITY": str, "COUNTY": str, "STATUS": str},
        )
        # Drop OUT-OF-SERVICE / RETIRED rows -- they may have stale coords
        # but won't be in any current LMP feed.
        if "STATUS" in df.columns:
            keep = df["STATUS"].fillna("").str.upper() == "IN SERVICE"
            df = df.loc[keep].copy()

        df["LATITUDE"] = pd.to_numeric(df["LATITUDE"], errors="coerce")
        df["LONGITUDE"] = pd.to_numeric(df["LONGITUDE"], errors="coerce")
        df["MAX_VOLT"] = pd.to_numeric(df["MAX_VOLT"], errors="coerce")
        df = df.dropna(subset=["LATITUDE", "LONGITUDE", "NAME"])

        rows: list[HifldRow] = []
        for r in df.itertuples(index=False):
            n = normalize(r.NAME)
            if not n:
                continue
            rows.append(
                HifldRow(
                    name=str(r.NAME),
                    state=str(r.STATE or "").upper(),
                    city=str(r.CITY or ""),
                    county=str(r.COUNTY or ""),
                    lat=float(r.LATITUDE),
                    lon=float(r.LONGITUDE),
                    max_volt=float(r.MAX_VOLT) if pd.notna(r.MAX_VOLT) else None,
                    norm_name=n,
                )
            )
        logger.info("HifldLookup: indexed %s active substations", len(rows))
        return cls(rows)

    def find_by_common_prefix(
        self,
        normalized_name: str,
        *,
        state: Optional[str] = None,
        states: Optional[Iterable[str]] = None,
        min_volt: Optional[float] = None,
        strict_state: bool = True,
        min_overlap: int = 6,
    ) -> Optional[HifldRow]:
        """Common-prefix-length HIFLD match (more permissive than `find_by_prefix`).

        Finds HIFLD entries that share a common prefix of at least
        `min_overlap` characters, even if neither full string is a prefix
        of the other. Catches cases like:

          PJM `BEECHDP`   ↔ HIFLD `BEECHWOODDP` -- shared prefix `BEECH` then diverge
          PJM `CLIFTNFG`  ↔ HIFLD `CLIFTONFORGE` -- shared prefix `CLIFT`
          PJM `KINGSFRK`  ↔ HIFLD `KINGSFORK`   -- shared prefix `KINGS`
          PJM `INDUSTPK`  ↔ HIFLD `INDUSTRIALPARK` -- shared `INDUST`

        Default `min_overlap=6` prevents most false positives.
        Tie-break: longest common prefix, then smallest length-diff,
        then highest voltage.
        """
        if not normalized_name or len(normalized_name) < min_overlap:
            return None

        target_states: Optional[set[str]] = None
        if state:
            target_states = {state.upper()}
        elif states:
            target_states = {s.upper() for s in states}

        rows_to_scan: list[HifldRow] = []
        if target_states:
            for r in self.rows:
                if r.state.upper() in target_states:
                    rows_to_scan.append(r)
            if not rows_to_scan and not strict_state:
                rows_to_scan = list(self.rows)
        else:
            rows_to_scan = list(self.rows)

        target_len = len(normalized_name)
        scored: list[tuple[tuple[int, int, float, str], HifldRow]] = []
        for r in rows_to_scan:
            n = r.norm_name
            if not n or len(n) < min_overlap:
                continue
            if min_volt is not None and (r.max_volt or 0) < min_volt:
                continue
            cp = 0
            for a, b in zip(normalized_name, n):
                if a == b:
                    cp += 1
                else:
                    break
            if cp < min_overlap:
                continue
            scored.append(((-cp, abs(len(n) - target_len), -(r.max_volt or 0), r.name), r))

        if not scored:
            return None
        scored.sort(key=lambda t: t[0])
        return scored[0][1]

    def find_by_prefix(
        self,
        normalized_name: str,
        *,
        state: Optional[str] = None,
        states: Optional[Iterable[str]] = None,
        min_volt: Optional[float] = None,
        strict_state: bool = True,
        min_overlap: int = 5,
    ) -> Optional[HifldRow]:
        """Bidirectional-prefix HIFLD match.

        Finds HIFLD entries where the input and the candidate share a
        prefix of at least `min_overlap` characters AND one is a prefix
        of the other. Useful when the ISO truncates substation names
        (PJM/MISO often truncate to 8 chars + add a circuit suffix).

        Examples (with min_overlap=5):
          PJM `BEECHDP` -> HIFLD `BEECHWOOD DP` (forward prefix; overlap 5)
          PJM `BANISTE` -> HIFLD `BANISTER`     (forward prefix; overlap 7)
          PJM `CENTRAL` -> HIFLD `CENTRALIA`    (forward prefix; overlap 7)

        Returns the highest-voltage candidate when multiple match.
        """
        if not normalized_name or len(normalized_name) < min_overlap:
            return None

        target_states: Optional[set[str]] = None
        if state:
            target_states = {state.upper()}
        elif states:
            target_states = {s.upper() for s in states}

        rows_to_scan: list[HifldRow] = []
        if target_states:
            for r in self.rows:
                if r.state.upper() in target_states:
                    rows_to_scan.append(r)
            if not rows_to_scan and not strict_state:
                rows_to_scan = list(self.rows)
        else:
            rows_to_scan = list(self.rows)

        candidates: list[HifldRow] = []
        for r in rows_to_scan:
            n = r.norm_name
            if not n:
                continue
            shorter, longer = (n, normalized_name) if len(n) <= len(normalized_name) else (normalized_name, n)
            if len(shorter) < min_overlap:
                continue
            if longer.startswith(shorter):
                candidates.append(r)

        if min_volt is not None:
            candidates = [c for c in candidates if (c.max_volt or 0) >= min_volt]
        if not candidates:
            return None
        # Tie-break: prefer the closest length match (so PJM `BEECHDP` picks
        # `BEECHWOOD DP` over a longer `BEECHFIELD` if both forward-match);
        # then highest voltage; then alphabetical.
        target_len = len(normalized_name)
        candidates.sort(
            key=lambda c: (abs(len(c.norm_name) - target_len), -(c.max_volt or 0), c.name),
        )
        return candidates[0]

    def find_by_name(
        self,
        normalized_name: str,
        *,
        state: Optional[str] = None,
        states: Optional[Iterable[str]] = None,
        min_volt: Optional[float] = None,
        strict_state: bool = True,
        try_prefix: bool = False,
        min_prefix_overlap: int = 5,
        try_common_prefix: bool = False,
        min_common_prefix: int = 6,
    ) -> Optional[HifldRow]:
        """Return the best HIFLD match, or None.

        Strategy:
          1. If `state` (or `states`) given, restrict candidates to those
             states. With `strict_state=True` (default), no global fallback
             -- that prevents cross-state false positives (e.g. an ERCOT
             RN matching a PA substation by coincidence). Set
             `strict_state=False` for ISOs that span state lines (PJM,
             MISO) where a state hint helps but global match is still
             acceptable.
          2. `min_volt` filters out small-distribution substations that
             are unlikely to host transmission-priced pnodes.
          3. Tie-break: highest MAX_VOLT, then alphabetical name (stable).
        """
        if not normalized_name:
            return None

        target_states: Optional[set[str]] = None
        if state:
            target_states = {state.upper()}
        elif states:
            target_states = {s.upper() for s in states}

        candidates: list[HifldRow] = []
        if target_states:
            for st in target_states:
                candidates.extend(self._by_state_norm.get((st, normalized_name), ()))
        if not candidates and (target_states is None or not strict_state):
            candidates = list(self._by_norm.get(normalized_name, ()))
        if min_volt is not None:
            candidates = [c for c in candidates if (c.max_volt or 0) >= min_volt]
        if not candidates and try_prefix:
            hit = self.find_by_prefix(
                normalized_name,
                state=state,
                states=states,
                min_volt=min_volt,
                strict_state=strict_state,
                min_overlap=min_prefix_overlap,
            )
            if hit is not None:
                return hit
        if not candidates and try_common_prefix:
            return self.find_by_common_prefix(
                normalized_name,
                state=state,
                states=states,
                min_volt=min_volt,
                strict_state=strict_state,
                min_overlap=min_common_prefix,
            )
        if not candidates:
            return None
        candidates.sort(key=lambda c: (-(c.max_volt or 0), c.name))
        return candidates[0]

    def __len__(self) -> int:
        return len(self.rows)
