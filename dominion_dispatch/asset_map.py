"""
Folium map: DER asset sites (lat/lon) and associated PJM pricing nodes (nodal area).

Program scope is **DOM**; optional GeoJSON outline from ``load_zones`` / PJM cache.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterable, Mapping, Optional

import folium
from folium import plugins

from dominion_dispatch.config import PJM_ZONE_DOM
from dominion_dispatch.dom_geocode import geocode_pnode_name_for_dom_program
from dominion_dispatch.load_zones import dom_zone_feature_collection
from dominion_dispatch.pnode_coords import (
    merge_pnode_coord_sources,
    pnode_id_to_latlon_from_definitions,
    pnode_id_to_name_from_definitions,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Map center: DOM zone centroid (matches data_acquisition.ZONE_CENTROIDS)
DOM_MAP_CENTER = (37.55, -78.0)
DOM_INITIAL_ZOOM = 8


def _device_site(dev: Mapping[str, Any]) -> Optional[tuple[float, float]]:
    lat, lon = dev.get("asset_lat"), dev.get("asset_lon")
    if lat is None or lon is None:
        return None
    try:
        return float(lat), float(lon)
    except (TypeError, ValueError):
        return None


def build_dom_program_asset_nodal_map(
    devices: Iterable[Mapping[str, Any]],
    *,
    project_root: Path,
    output_html: Path,
    pnode_coords: Optional[dict[str, tuple[float, float]]] = None,
    session: Optional["Session"] = None,
    include_dom_boundary: bool = True,
    geocode_missing_pnodes: bool = False,
    pnode_definitions_df: Optional[Any] = None,
) -> Path:
    """
    Build an interactive map with:

    - Optional **DOM** commercial-zone outline (GeoJSON).
    - **Pricing node** markers (blue) at ``pnode_coords`` for each device's ``primary_pnode_id``.
    - **Asset** markers (green) at ``asset_lat`` / ``asset_lon`` when provided.
    - **Link lines** between asset and primary pnode when both coordinates exist.

    ``pnode_coords`` maps ``str(pnode_id)`` -> ``(lat, lon)``. Supply via JSON, PJM
    definitions frame, and/or set ``geocode_missing_pnodes`` (uses Nominatim; slow).

    ``pnode_definitions_df``: optional ``DataFrame`` from ``pull_pnode_list("DOM")`` to
    fill missing coords / names before geocoding.
    """
    dev_list = [dict(d) for d in devices]
    coords: dict[str, tuple[float, float]] = dict(pnode_coords or {})

    id_to_name: dict[str, str] = {}
    if pnode_definitions_df is not None and not pnode_definitions_df.empty:
        coords = merge_pnode_coord_sources(
            pnode_id_to_latlon_from_definitions(pnode_definitions_df),
            coords,
        )
        id_to_name = pnode_id_to_name_from_definitions(pnode_definitions_df)

    if geocode_missing_pnodes:
        import requests

        sess = requests.Session()
        seen: set[str] = set()
        for dev in dev_list:
            pid = str(dev.get("primary_pnode_id") or dev.get("pnode_id") or "").strip()
            if not pid or pid in coords or pid in seen:
                continue
            seen.add(pid)
            pname = (
                dev.get("primary_pnode_name")
                or dev.get("pnode_name")
                or id_to_name.get(pid)
            )
            if not pname:
                logger.warning("Cannot geocode pnode %s: no name", pid)
                continue
            hit = geocode_pnode_name_for_dom_program(str(pname), session=sess)
            time.sleep(1.1)
            if hit:
                coords[pid] = (hit[0], hit[1])
                logger.info("Geocoded pnode %s (%s)", pid, pname[:40])
            else:
                logger.warning("Geocode miss for pnode %s (%s)", pid, pname[:40])

    # Map center: mean of available points, else DOM default
    pts: list[tuple[float, float]] = list(coords.values())
    for dev in dev_list:
        s = _device_site(dev)
        if s:
            pts.append(s)
    if pts:
        center = (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))
    else:
        center = DOM_MAP_CENTER

    m = folium.Map(location=[center[0], center[1]], zoom_start=DOM_INITIAL_ZOOM, tiles="cartodbpositron")
    fg_dom = folium.FeatureGroup(name=f"PJM zone {PJM_ZONE_DOM} (outline)", show=True)
    fg_pnode = folium.FeatureGroup(name="Pricing nodes (pnode)", show=True)
    fg_asset = folium.FeatureGroup(name="DER assets", show=True)
    fg_links = folium.FeatureGroup(name="Asset → pnode", show=True)

    if include_dom_boundary:
        fc = dom_zone_feature_collection(project_root, session=session)
        if fc.get("features"):
            folium.GeoJson(
                fc,
                name="dom_boundary",
                style_function=lambda _f: {"fillOpacity": 0.05, "weight": 2},
            ).add_to(fg_dom)
            fg_dom.add_to(m)
        else:
            logger.info("No DOM boundary GeoJSON available (cache DB empty); outline skipped")

    for dev in dev_list:
        pid = str(dev.get("primary_pnode_id") or dev.get("pnode_id") or "").strip()
        if not pid:
            continue
        label = dev.get("asset_display_name") or dev.get("device_id_external") or dev.get("device_id")
        site = _device_site(dev)
        plat, plon = None, None
        if pid in coords:
            plat, plon = coords[pid]
            pname = (
                dev.get("primary_pnode_name")
                or dev.get("pnode_name")
                or id_to_name.get(pid, pid)
            )
            folium.CircleMarker(
                location=[plat, plon],
                radius=6,
                color="#1f77b4",
                fill=True,
                fill_color="#aec7e8",
                weight=2,
                popup=folium.Popup(
                    f"<b>Pnode</b> {pid}<br><small>{pname}</small>",
                    max_width=280,
                ),
            ).add_to(fg_pnode)

        if site:
            folium.CircleMarker(
                location=[site[0], site[1]],
                radius=8,
                color="#2ca02c",
                fill=True,
                fill_color="#98df8a",
                weight=2,
                popup=folium.Popup(
                    f"<b>Asset</b> {label}<br>Pnode {pid}",
                    max_width=280,
                ),
            ).add_to(fg_asset)
            if plat is not None and plon is not None:
                folium.PolyLine(
                    locations=[list(site), [plat, plon]],
                    color="#9467bd",
                    weight=2,
                    opacity=0.75,
                ).add_to(fg_links)

    fg_pnode.add_to(m)
    fg_asset.add_to(m)
    fg_links.add_to(m)
    plugins.Fullscreen().add_to(m)
    folium.LayerControl(collapsed=False).add_to(m)

    output_html.parent.mkdir(parents=True, exist_ok=True)
    m.save(str(output_html))
    logger.info("Wrote asset/nodal map to %s", output_html)
    return output_html
