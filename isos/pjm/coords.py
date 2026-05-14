"""PJM pnode-name normalizer for HIFLD matching.

PJM LOAD pnode names follow `<SUBSTATION_NAME><VOLTAGE_KV> KV   <CIRCUIT>`
patterns, e.g.:

  `ACCA    13 KV   TX1`            -> "ACCA"
  `BLBRANDP69 KV   TX1`            -> "BLBRANDP"
  `ALTAVSTA13 KV   TX2TLOAD`       -> "ALTAVSTA"
  `BRADDOCK 230 KV   TR3`          -> "BRADDOCK"
  `TYSONS  230KV TR3`              -> "TYSONS"

Strategy: take everything before the first run of "<digits> KV" or
"<digits>KV" -- the substation name precedes the voltage marker.
Strip whitespace, run through the shared HIFLD normalizer.
"""
from __future__ import annotations

import re

from isos.coords.hifld import normalize

_SUBSTATION_VOLTAGE_RE = re.compile(r"^(.*?)\s*\d+\s*KV", re.IGNORECASE)


_TRAILING_DIGITS_RE = re.compile(r"\d+$")


def normalize_load_pnode_name(pname: str) -> list[str]:
    """Extract substation-name candidates from a PJM LOAD pnode name.

    Returns a list of candidate normalized strings (most-specific first).
    The matcher should also be invoked with `try_prefix=True` so that
    truncated PJM names (max 8 chars in the catalog) match the full
    HIFLD name -- e.g. PJM `BANISTE4` -> HIFLD `BANISTER`.

    Examples:
      `ACCA    13 KV   TX1`        -> ["ACCA"]
      `BANISTE435 KV   BUS2LOAD`   -> ["BANISTE", "BANISTE4"]
      `CHATHAM413 KV   TX1`        -> ["CHATHAM", "CHATHAM4"]
      `BEECHDP69 KV    TX1`        -> ["BEECHDP"]
      `FOURRIVR230 KV  TX1`        -> ["FOURRIVR"]
    """
    if not pname:
        return []
    p = str(pname).strip().upper()

    # Pull everything before the first "<digits> KV" or "<digits>KV".
    m = _SUBSTATION_VOLTAGE_RE.match(p)
    if m:
        sub_name = m.group(1).strip()
    else:
        sub_name = p.split()[0] if p.split() else ""

    if not sub_name:
        return []

    raw = normalize(sub_name)
    if len(raw) < 3:
        return []

    # Build candidate list. Most useful: with trailing digits stripped
    # (PJM circuit number suffix), then the raw form as fallback.
    stripped = _TRAILING_DIGITS_RE.sub("", raw) or raw
    candidates: list[str] = []
    if stripped and stripped not in candidates:
        candidates.append(stripped)
    if raw not in candidates:
        candidates.append(raw)
    return candidates
