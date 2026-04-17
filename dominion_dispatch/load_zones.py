"""
PJM **load zone** (commercial pricing zone) polygons for **DOM** (Dominion Virginia).

Use with ``dominion_dispatch.asset_map`` to outline where enrolled assets sit relative
to nodal pricing geography. The repo does **not** ship pre-built GeoJSON in-tree; boundaries come from the
same assets the classifier already uses:

1. **Pipeline cache** — after ``fetch_zone_boundaries()`` from ``src.pjm_gis``,
   polygons live at ``data/geo/pjm_zone_boundaries.geojson`` with
   ``properties.pjm_zone`` set to short codes like ``DOM``.
2. **Postgres** — ``zones.boundary_geojson`` on the PJM ``zones`` row for
   ``zone_code='DOM'``, populated when ``PipelineRun`` / ``write_zone_boundaries``
   has been executed for PJM.

Use these for siting / map UX; **DA congestion** itself still comes from PJM
``da_hrl_lmps`` keyed by **pnode**, not from the polygon geometry.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional, TYPE_CHECKING

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

DOM_ZONE_CODE = "DOM"


def dom_feature_from_pjm_zone_cache(cache_path: Path) -> Optional[dict[str, Any]]:
    """
    Return a single GeoJSON *Feature* for DOM from ``pjm_zone_boundaries.geojson``.

    ``cache_path`` should point to the file (typically
    ``<project>/data/geo/pjm_zone_boundaries.geojson``).
    """
    if not cache_path.is_file():
        logger.info("PJM zone boundary cache missing: %s", cache_path)
        return None
    try:
        fc = json.loads(cache_path.read_text())
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("Could not read zone cache %s: %s", cache_path, e)
        return None
    for feat in fc.get("features", []):
        props = feat.get("properties") or {}
        if props.get("pjm_zone") == DOM_ZONE_CODE:
            return feat
    logger.info("No DOM feature in %s", cache_path)
    return None


def dom_boundary_from_zones_table(session: "Session") -> Optional[dict[str, Any]]:
    """Return ``zones.boundary_geojson`` geometry dict for PJM zone ``DOM``, if present."""
    from sqlalchemy import func, select

    from app.models.zone import Zone
    from app.models.iso import ISO

    row = session.execute(
        select(Zone.boundary_geojson)
        .join(ISO, Zone.iso_id == ISO.id)
        .where(func.lower(ISO.iso_code) == "pjm", Zone.zone_code == DOM_ZONE_CODE)
    ).scalar_one_or_none()
    if row is None:
        return None
    return row  # already a dict (GeoJSON geometry) in typical pipeline writes


def dom_zone_feature_collection(
    project_root: Path,
    session: Optional["Session"] = None,
) -> dict[str, Any]:
    """
    Build a minimal FeatureCollection for DOM: prefer DB geometry, else GIS cache.
    """
    geom: Optional[dict[str, Any]] = None
    source = "none"
    if session is not None:
        geom = dom_boundary_from_zones_table(session)
        if geom is not None:
            source = "postgres.zones.boundary_geojson"
    if geom is None:
        feat = dom_feature_from_pjm_zone_cache(project_root / "data" / "geo" / "pjm_zone_boundaries.geojson")
        if feat is not None:
            source = "cache.pjm_zone_boundaries"
            return {"type": "FeatureCollection", "features": [feat], "properties": {"source": source}}
        return {"type": "FeatureCollection", "features": [], "properties": {"source": source}}
    return {
        "type": "FeatureCollection",
        "features": [{"type": "Feature", "properties": {"pjm_zone": DOM_ZONE_CODE}, "geometry": geom}],
        "properties": {"source": source},
    }
