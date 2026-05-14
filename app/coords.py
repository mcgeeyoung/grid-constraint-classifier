"""Per-utility pricing-node coordinate resolution (shape B).

Source-of-truth precedence (highest wins on conflict):

  1. `utilities/<id>/<pnode_coords_path>`  -- per-utility overrides
                                              (hand-curated pilots, region-
                                              specific corrections)
  2. `isos/<iso_lower>/refdata/pnode_coords_<iso_lower>.json`
                                           -- ISO-wide HIFLD pipeline output
                                              (long-tail coverage)

Both files are optional; missing files are silently treated as empty.
The merged dict is cached per `utility_id` for the life of the
process. Re-importing the module clears the cache.
"""
from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Optional

from wcgrid.utilities import UtilityConfig, utility_dir

logger = logging.getLogger(__name__)

_REPO = Path(__file__).resolve().parents[1]


def _iso_coords_path(iso: str) -> Path:
    """Resolve wcgrid's packaged ISO refdata file for the given iso.

    PJM uses a zone-scoped filename (``pnode_coords_pjm_dom.json``) because
    the LOAD-pnode catalogue varies per zone; every other ISO follows the
    ``pnode_coords_<iso_lower>.json`` convention.
    """
    from importlib import resources

    iso_l = iso.lower()
    filename = "pnode_coords_pjm_dom.json" if iso_l == "pjm" else f"pnode_coords_{iso_l}.json"
    root = resources.files(f"wcgrid.isos.{iso_l}")
    return Path(str(root)) / "refdata" / filename


def _load_coord_file(path: Path) -> dict[str, tuple[float, float]]:
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        logger.error("Coord file unreadable %s: %s", path, exc)
        return {}
    out: dict[str, tuple[float, float]] = {}
    for k, v in raw.items():
        if k.startswith("_"):
            continue
        if isinstance(v, (list, tuple)) and len(v) >= 2:
            try:
                out[str(k).strip()] = (float(v[0]), float(v[1]))
            except (TypeError, ValueError):
                continue
        elif isinstance(v, dict):
            lat = v.get("lat") or v.get("latitude")
            lon = v.get("lon") or v.get("longitude")
            if lat is None or lon is None:
                continue
            try:
                out[str(k).strip()] = (float(lat), float(lon))
            except (TypeError, ValueError):
                continue
    return out


@lru_cache(maxsize=32)
def load_pnode_coords_for(utility_id: str) -> dict[str, tuple[float, float]]:
    """Resolve coords for `utility_id`. Cached per utility_id."""
    from wcgrid.utilities import load_utility  # local to avoid cycle at import time

    cfg: UtilityConfig = load_utility(utility_id)
    iso_path = _iso_coords_path(cfg.iso)
    util_path = utility_dir(cfg.utility_id) / cfg.pnode_coords_path

    iso_coords = _load_coord_file(iso_path)
    util_coords = _load_coord_file(util_path)

    merged: dict[str, tuple[float, float]] = {}
    merged.update(iso_coords)
    merged.update(util_coords)  # utility wins

    logger.info(
        "load_pnode_coords_for %s: iso=%s (%s coords) + utility (%s coords) = %s merged",
        utility_id, cfg.iso, len(iso_coords), len(util_coords), len(merged),
    )
    return merged


def clear_cache() -> None:
    load_pnode_coords_for.cache_clear()
