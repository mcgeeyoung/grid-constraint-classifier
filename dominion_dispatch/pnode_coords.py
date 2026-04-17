"""
Resolve pricing-node (pnode) coordinates for map layers.

PJM ``pnodes`` DataMiner responses vary by vintage; we probe common column names.
External JSON is supported for hand-curated nodal points.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional

import pandas as pd

logger = logging.getLogger(__name__)


def load_pnode_coords_json(path: Path) -> dict[str, tuple[float, float]]:
    """
    Load a JSON dict keyed by ``pnode_id`` string.

    Values may be ``[lat, lon]``, ``{"lat": .., "lon": ..}``, or ``{"latitude": .., "longitude": ..}``.
    """
    raw = json.loads(path.read_text())
    if not isinstance(raw, dict):
        raise ValueError("pnode coords JSON must be an object keyed by pnode_id")
    out: dict[str, tuple[float, float]] = {}
    for k, v in raw.items():
        pid = str(k).strip()
        if isinstance(v, (list, tuple)) and len(v) >= 2:
            out[pid] = (float(v[0]), float(v[1]))
        elif isinstance(v, dict):
            lat = v.get("lat") or v.get("latitude")
            lon = v.get("lon") or v.get("longitude")
            if lat is not None and lon is not None:
                out[pid] = (float(lat), float(lon))
    logger.info("Loaded %s pnode coordinate overrides from %s", len(out), path)
    return out


def pnode_id_to_latlon_from_definitions(df: pd.DataFrame) -> dict[str, tuple[float, float]]:
    """
    Best-effort parse of lat/lon from a PJM ``query_pnodes`` / ``pull_pnode_list`` frame.
    """
    if df.empty or "pnode_id" not in df.columns:
        return {}

    lat_col: Optional[str] = None
    lon_col: Optional[str] = None
    for c in df.columns:
        cl = c.lower()
        if lat_col is None and cl in ("latitude", "lat", "aggregate_point_latitude", "aggregate_meter_latitude"):
            lat_col = c
        if lon_col is None and cl in ("longitude", "lon", "aggregate_point_longitude", "aggregate_meter_longitude"):
            lon_col = c
    if not lat_col or not lon_col:
        logger.info(
            "Pnode definitions frame has no recognizable lat/lon columns (got %s)",
            list(df.columns),
        )
        return {}

    sub = df[["pnode_id", lat_col, lon_col]].copy()
    sub["pnode_id"] = sub["pnode_id"].astype(str)
    sub[lat_col] = pd.to_numeric(sub[lat_col], errors="coerce")
    sub[lon_col] = pd.to_numeric(sub[lon_col], errors="coerce")
    sub = sub.dropna(subset=[lat_col, lon_col])
    out: dict[str, tuple[float, float]] = {}
    for _, row in sub.iterrows():
        out[str(row["pnode_id"])] = (float(row[lat_col]), float(row[lon_col]))
    logger.info("Parsed %s pnode lat/lon pairs from definitions", len(out))
    return out


def merge_pnode_coord_sources(
    *sources: dict[str, tuple[float, float]],
) -> dict[str, tuple[float, float]]:
    """Later dicts override earlier keys."""
    merged: dict[str, tuple[float, float]] = {}
    for s in sources:
        merged.update(s)
    return merged


def pnode_id_to_name_from_definitions(df: pd.DataFrame) -> dict[str, str]:
    """Map ``pnode_id`` string -> ``pnode_name`` when present."""
    if df.empty or "pnode_id" not in df.columns or "pnode_name" not in df.columns:
        return {}
    d = df[["pnode_id", "pnode_name"]].drop_duplicates(subset=["pnode_id"])
    d["pnode_id"] = d["pnode_id"].astype(str)
    return {str(row["pnode_id"]): str(row["pnode_name"]) for _, row in d.iterrows()}
