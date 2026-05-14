"""Generic per-ISO pnode-name -> HIFLD coord matcher."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Callable, Iterable, Optional

from isos.coords.hifld import HifldLookup

logger = logging.getLogger(__name__)


def match_pnode_names_to_hifld(
    catalog: Iterable[tuple[str, str]],
    lookup: HifldLookup,
    *,
    normalize_name: Callable[[str], str | list[str]],
    state: Optional[str] = None,
    states: Optional[Iterable[str]] = None,
    min_volt: Optional[float] = None,
    strict_state: bool = True,
    try_prefix: bool = False,
    min_prefix_overlap: int = 5,
    try_common_prefix: bool = False,
    min_common_prefix: int = 6,
    extras: Optional[dict[str, tuple[float, float]]] = None,
) -> tuple[dict[str, tuple[float, float]], dict[str, str]]:
    """Match a (pnode_id, pnode_name) catalog against HIFLD.

    Args:
      catalog: iterable of (pnode_id, pnode_name) pairs from the ISO driver.
      lookup: pre-built HifldLookup.
      normalize_name: callable that turns a raw pnode_name into either
        a single normalized substation token or a **list** of candidate
        tokens to try in order. Returning "" or [] skips the pnode.
        Per-ISO logic lives here.
      state / states: 2-letter state(s) to restrict the search. ERCOT is
        single-state ("TX"); PJM/MISO span many states.
      strict_state: when True (default), no global fallback if state given.
        Eliminates cross-state false positives. Set False for ISOs whose
        pnode catalog is occasionally state-mislabeled.
      min_volt: drop HIFLD candidates below this voltage (kV).
      extras: optional pre-set `{pnode_id: (lat, lon)}` to seed the result
        before HIFLD matching. Useful for hand-curated zones, hubs, DC ties.

    Returns:
      (coords, notes) where coords is `{pnode_id: (lat, lon)}` (only matched
      ids) and notes is `{pnode_id: human-readable match note}`.
    """
    coords: dict[str, tuple[float, float]] = dict(extras or {})
    notes: dict[str, str] = {pid: "[seeded extras]" for pid in coords}

    catalog_list = list(catalog)
    matched = len(coords)
    skipped_normalized = 0
    no_hit = 0

    for pid, pname in catalog_list:
        pid = str(pid)
        if pid in coords:
            continue
        result = normalize_name(pname or "")
        candidates: list[str] = (
            [c for c in result if c] if isinstance(result, (list, tuple)) else ([result] if result else [])
        )
        if not candidates:
            skipped_normalized += 1
            continue

        hit = None
        winning_norm = ""
        for norm in candidates:
            hit = lookup.find_by_name(
                norm,
                state=state,
                states=states,
                min_volt=min_volt,
                strict_state=strict_state,
                try_prefix=try_prefix,
                min_prefix_overlap=min_prefix_overlap,
                try_common_prefix=try_common_prefix,
                min_common_prefix=min_common_prefix,
            )
            if hit is not None:
                winning_norm = norm
                break
        if hit is None:
            no_hit += 1
            continue
        coords[pid] = (hit.lat, hit.lon)
        notes[pid] = (
            f"{pname!r} norm={winning_norm!r} -> HIFLD {hit.name!r} "
            f"({hit.city}, {hit.state}, {hit.max_volt}kV)"
        )
        matched += 1

    logger.info(
        "HIFLD match: %s/%s pnodes matched (skipped_normalized=%s, no_hit=%s)",
        matched, len(catalog_list) + len(extras or {}), skipped_normalized, no_hit,
    )
    return coords, notes


def write_coord_json(
    out_path: Path,
    coords: dict[str, tuple[float, float]],
    *,
    notes: Optional[dict[str, str]] = None,
    source: str = "",
    iso_id: str = "",
    catalog_size: Optional[int] = None,
) -> None:
    """Write a coords JSON in the dominion-style shape.

    Top-level shape: `{pnode_id: [lat, lon], "_source": ..., "_match_notes": {...}}`
    -- compatible with `dominion_dispatch.pnode_coords.load_pnode_coords_json`.
    """
    payload: dict = {}
    if source:
        payload["_source"] = source
    if iso_id:
        payload["_iso_id"] = iso_id
    if catalog_size is not None:
        payload["_catalog_size"] = catalog_size
        payload["_matched"] = len(coords)
        if catalog_size > 0:
            payload["_match_rate"] = round(100 * len(coords) / catalog_size, 1)
    if notes:
        payload["_match_notes"] = notes
    for pid, (lat, lon) in sorted(coords.items()):
        payload[pid] = [lat, lon]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2))
    logger.info("Wrote %s pnode coords to %s", len(coords), out_path)
