"""Folium map: DER asset sites + ISO pricing-node markers, parameterized by iso_id.

Generalizes `dominion_dispatch.asset_map.build_dom_program_asset_nodal_map`
to work for any of the eight registered ISOs (PJM, CAISO, NYISO, MISO,
ISONE, SPP, WECC, ERCOT). Pulls hand-curated + HIFLD-matched pnode
coordinates from the per-ISO `refdata/pnode_coords_<iso>.json` file
that `isos/coords` generates.

Boundary polygons (zone outlines) are optional and ISO-specific;
callers can pass a GeoJSON FeatureCollection or omit. The asset
markers, pnode markers, and link lines are universal.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional

import folium
from folium import plugins

logger = logging.getLogger(__name__)

# Default per-ISO map center + zoom. Used when no asset/pnode data
# constrains the view.
ISO_DEFAULT_CENTER: dict[str, tuple[float, float, int]] = {
    "PJM":   (39.5, -77.5, 6),    # Mid-Atlantic
    "CAISO": (37.0, -120.0, 6),   # California
    "NYISO": (43.0, -75.0, 7),    # NY State
    "MISO":  (42.0, -91.0, 5),    # Upper Midwest + South
    "ISONE": (43.5, -71.5, 7),    # New England
    "SPP":   (38.5, -97.0, 5),    # Plains
    "WECC":  (40.0, -115.0, 4),   # West-wide
    "ERCOT": (31.5, -98.5, 6),    # Texas
}

# Repo location of per-ISO coords files written by isos.coords pipeline.
def default_coords_path(iso_id: str, repo_root: Path) -> Path:
    """isos/<iso>/refdata/pnode_coords_<iso>.json convention."""
    iso = iso_id.lower()
    # PJM uses zone-scoped filename; surface as a separate fallback.
    if iso == "pjm":
        return repo_root / "isos" / "pjm" / "refdata" / "pnode_coords_pjm_dom.json"
    return repo_root / "isos" / iso / "refdata" / f"pnode_coords_{iso}.json"


def load_iso_pnode_coords(
    iso_id: str,
    repo_root: Path,
    *,
    extra_path: Optional[Path] = None,
) -> dict[str, tuple[float, float]]:
    """Load coords keyed by `pnode_id` (string).

    Sources, in priority order:
      1. `extra_path` (caller-supplied JSON; overrides the rest).
      2. `isos/<iso>/refdata/pnode_coords_<iso>.json` (the HIFLD pipeline
         output, plus hand-curated centroids per ISO).

    Returns empty dict if no source resolves; the caller can still draw
    the asset markers without pnode markers.
    """
    coords: dict[str, tuple[float, float]] = {}
    primary = default_coords_path(iso_id, repo_root)
    if primary.is_file():
        coords.update(_load_coords_file(primary))
    if extra_path is not None and extra_path.is_file():
        # Caller overrides win; load last so they overwrite.
        coords.update(_load_coords_file(extra_path))
    if not coords:
        logger.info("No pnode coords found for iso_id=%s (looked at %s)", iso_id, primary)
    return coords


def _load_coords_file(path: Path) -> dict[str, tuple[float, float]]:
    raw = json.loads(path.read_text())
    out: dict[str, tuple[float, float]] = {}
    for k, v in raw.items():
        if k.startswith("_"):
            continue  # _source / _match_notes / etc.
        if isinstance(v, (list, tuple)) and len(v) >= 2:
            try:
                out[str(k)] = (float(v[0]), float(v[1]))
            except (TypeError, ValueError):
                continue
        elif isinstance(v, dict):
            lat = v.get("lat") or v.get("latitude")
            lon = v.get("lon") or v.get("longitude")
            if lat is not None and lon is not None:
                try:
                    out[str(k)] = (float(lat), float(lon))
                except (TypeError, ValueError):
                    continue
    logger.info("Loaded %s pnode coords from %s", len(out), path)
    return out


def _device_site(dev: Mapping[str, Any]) -> Optional[tuple[float, float]]:
    lat, lon = dev.get("asset_lat"), dev.get("asset_lon")
    if lat is None or lon is None:
        return None
    try:
        return float(lat), float(lon)
    except (TypeError, ValueError):
        return None


def build_iso_asset_nodal_map(
    iso_id: str,
    devices: Iterable[Mapping[str, Any]],
    *,
    repo_root: Path,
    output_html: Path,
    pnode_coords: Optional[dict[str, tuple[float, float]]] = None,
    extra_coords_path: Optional[Path] = None,
    boundary_geojson: Optional[dict[str, Any]] = None,
    boundary_label: Optional[str] = None,
    participation: Optional[Mapping[str, Mapping[str, Any]]] = None,
    title: Optional[str] = None,
) -> Path:
    """Build an interactive Folium map for any registered ISO.

    Args:
      iso_id: e.g. `"PJM"`, `"ERCOT"`, `"WECC"` -- any iso_id from `isos.list_isos()`.
      devices: iterable of dicts with keys `device_id_external` (or
        `device_id`), `primary_pnode_id` (or `pnode_id`), and optional
        `asset_lat` / `asset_lon` / `asset_display_name`.
      repo_root: repo root path; the function looks under
        `<repo>/isos/<iso>/refdata/` for the canonical coords JSON.
      output_html: where to write the .html (parent dir created).
      pnode_coords: optional pre-built `{pnode_id: (lat, lon)}`. Takes
        priority over the on-disk JSON.
      extra_coords_path: optional override JSON. Loaded after the
        canonical file, so its keys win.
      boundary_geojson: optional GeoJSON FeatureCollection for zone /
        BAA boundaries. ISO-specific; supplied by the caller (e.g.
        `dominion_dispatch.load_zones.dom_zone_feature_collection`
        builds DOM; per-utility maps in WECC could pass BA polygons).
      boundary_label: legend label for the boundary layer.
      participation: optional `{device_id: {...stats...}}` for richer
        asset-marker popups (matches the dominion-demo schema).
      title: optional `<h3>` title injected at the top of the map.

    Returns the resolved `output_html` path.
    """
    iso = iso_id.upper()
    dev_list = [dict(d) for d in devices]

    coords: dict[str, tuple[float, float]] = dict(pnode_coords or {})
    if not coords:
        coords = load_iso_pnode_coords(iso, repo_root, extra_path=extra_coords_path)

    # Map center: mean of available points, else ISO default.
    pts: list[tuple[float, float]] = list(coords.values())
    for dev in dev_list:
        s = _device_site(dev)
        if s:
            pts.append(s)
    if pts:
        center = (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))
        zoom = ISO_DEFAULT_CENTER.get(iso, (40.0, -98.0, 4))[2]
    else:
        c = ISO_DEFAULT_CENTER.get(iso, (40.0, -98.0, 4))
        center = (c[0], c[1])
        zoom = c[2]

    m = folium.Map(location=[center[0], center[1]], zoom_start=zoom, tiles="cartodbpositron")

    fg_boundary = folium.FeatureGroup(name=boundary_label or f"{iso} boundary", show=True)
    fg_pnode = folium.FeatureGroup(name="Pricing nodes", show=True)
    fg_asset = folium.FeatureGroup(name="DER assets", show=True)
    fg_links = folium.FeatureGroup(name="Asset -> pnode", show=True)

    if boundary_geojson and boundary_geojson.get("features"):
        folium.GeoJson(
            boundary_geojson,
            name=boundary_label or "boundary",
            style_function=lambda _f: {"fillOpacity": 0.05, "weight": 2, "color": "#444"},
        ).add_to(fg_boundary)
        fg_boundary.add_to(m)

    # Pnode markers (blue) and asset markers (green) with optional link lines.
    drawn_pnodes: set[str] = set()
    for dev in dev_list:
        pid = str(dev.get("primary_pnode_id") or dev.get("pnode_id") or "").strip()
        if not pid:
            continue
        site = _device_site(dev)
        plat, plon = (None, None)
        if pid in coords:
            plat, plon = coords[pid]
            if pid not in drawn_pnodes:
                pname = dev.get("primary_pnode_name") or dev.get("pnode_name") or pid
                folium.CircleMarker(
                    location=[plat, plon],
                    radius=6,
                    color="#1f77b4",
                    fill=True,
                    fill_color="#aec7e8",
                    weight=2,
                    popup=folium.Popup(
                        f"<b>Pnode</b> {pid}<br><small>{pname}</small><br><i>{iso}</i>",
                        max_width=280,
                    ),
                ).add_to(fg_pnode)
                drawn_pnodes.add(pid)

        if site:
            label = (
                dev.get("asset_display_name")
                or dev.get("device_id_external")
                or dev.get("device_id")
                or "(unnamed)"
            )
            dev_id = dev.get("device_id_external") or dev.get("device_id")
            stats = participation.get(dev_id) if participation and dev_id else None
            if stats and stats.get("total_hours"):
                pct = float(stats.get("participation_pct") or 0.0)
                radius = 6 + 14 * min(pct / 50.0, 1.0)
                popup_html = (
                    f"<b>Asset</b> {label}<br>"
                    f"Pnode {pid}<br>"
                    f"<hr style='margin:4px 0'>"
                    f"<b>Participation</b> "
                    f"({stats.get('runs', 0)} DA days, {stats.get('total_hours', 0)} hrs)<br>"
                    f"Any dispatch: {stats.get('any_dispatch_hours', 0)} hrs ({pct:.1f}%)<br>"
                    f"Mandatory: {stats.get('mandatory_hours', 0)} hrs"
                )
            else:
                radius = 8
                popup_html = f"<b>Asset</b> {label}<br>Pnode {pid}<br><i>{iso}</i>"
            folium.CircleMarker(
                location=[site[0], site[1]],
                radius=radius,
                color="#2ca02c",
                fill=True,
                fill_color="#98df8a",
                weight=2,
                popup=folium.Popup(popup_html, max_width=320),
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

    if title:
        title_html = (
            f"<h3 style='font-family: Inter, sans-serif; margin: 8px;'>"
            f"{title}</h3>"
        )
        m.get_root().html.add_child(folium.Element(title_html))

    plugins.Fullscreen().add_to(m)
    folium.LayerControl(collapsed=False).add_to(m)

    output_html.parent.mkdir(parents=True, exist_ok=True)
    m.save(str(output_html))
    logger.info("Wrote %s asset/pnode map to %s (devices=%s, pnodes=%s)",
                iso, output_html, len(dev_list), len(coords))
    return output_html
