"""
Interactive Folium map builder for grid constraint classification results.

Parameterized for any ISO: map center, zone key, and labels are all configurable.
"""

import logging
import random
from pathlib import Path
from typing import Optional

import pandas as pd
from jinja2 import Template
from branca.element import MacroElement

logger = logging.getLogger(__name__)

# Classification -> color mapping
CLASS_COLORS = {
    "transmission": "#e74c3c",   # Red
    "generation": "#3498db",     # Blue
    "both": "#9b59b6",           # Purple
    "unconstrained": "#2ecc71",  # Green
}

TIER_COLORS = {
    "critical": "#e74c3c",   # Red
    "elevated": "#e67e22",   # Orange
    "moderate": "#f1c40f",   # Yellow
    "low": "#27ae60",        # Green
}

# HIFLD Electric Power Transmission Lines FeatureServer
HIFLD_TX_URL = (
    "https://services1.arcgis.com/Hp6G80Pky0om7QvQ/arcgis/rest/services/"
    "Electric_Power_Transmission_Lines/FeatureServer/0"
)


class _EsriTransmissionLayer(MacroElement):
    """
    MacroElement that injects esri-leaflet and adds a live HIFLD
    transmission FeatureLayer directly to the Folium map.
    """

    _template = Template("""
        {% macro header(this, kwargs) %}
        <script src="https://unpkg.com/esri-leaflet@3.0.12/dist/esri-leaflet.js"></script>
        {% endmacro %}

        {% macro script(this, kwargs) %}
        var {{ this.get_name() }} = L.esri.featureLayer({
            url: '{{ this.url }}',
            where: "{{ this.where_clause }}",
            style: function(feature) {
                var v = (feature.properties || {}).VOLTAGE || 0;
                if (v >= 500) return {color: '#cc0000', weight: 3, opacity: 0.8};
                if (v >= 345) return {color: '#e65c00', weight: 2.5, opacity: 0.7};
                if (v >= 230) return {color: '#ff8c00', weight: 1.5, opacity: 0.6};
                return {color: '#aaa', weight: 1, opacity: 0.4};
            },
            onEachFeature: function(feature, layer) {
                var p = feature.properties || {};
                layer.bindTooltip(
                    (p.VOLTAGE || '?') + ' kV | ' + (p.OWNER || 'Unknown')
                        + (p.SUB_1 ? '<br>' + p.SUB_1 + ' \\u2192 ' + (p.SUB_2 || '?') : ''),
                    {sticky: true}
                );
            }
        }).addTo({{ this._parent.get_name() }});

        setTimeout(function() {
            var overlays = document.querySelectorAll('.leaflet-control-layers-overlays');
            if (overlays.length > 0) {
                var label = document.createElement('label');
                var div = document.createElement('div');
                var input = document.createElement('input');
                input.type = 'checkbox';
                input.className = 'leaflet-control-layers-selector';
                input.checked = true;
                input.addEventListener('change', function() {
                    if (this.checked) {
                        {{ this.get_name() }}.addTo({{ this._parent.get_name() }});
                    } else {
                        {{ this._parent.get_name() }}.removeLayer({{ this.get_name() }});
                    }
                });
                var span = document.createElement('span');
                span.textContent = ' HIFLD Transmission Lines';
                label.appendChild(div);
                div.appendChild(input);
                div.appendChild(span);
                overlays[0].appendChild(label);
            }
        }, 200);
        {% endmacro %}
    """)

    def __init__(self, url, where_clause="1=1"):
        super().__init__()
        self._name = "EsriTransmissionLayer"
        self.url = url
        self.where_clause = where_clause


def create_interactive_map(
    classification_df: pd.DataFrame,
    zone_centroids: dict,
    recommendations: list[dict],
    data_center_locations: list[dict],
    transmission_geojson: Optional[dict] = None,
    pnode_data: Optional[dict] = None,
    zone_boundaries: Optional[dict] = None,
    backbone_geojson: Optional[dict] = None,
    output_path: Optional[Path] = None,
    map_center: tuple[float, float] = (39.5, -78.0),
    map_zoom: int = 6,
    iso_name: str = "PJM",
    zone_key: str = "pjm_zone",
) -> str:
    """
    Create an interactive Folium map showing constraint classifications.

    Args:
        classification_df: Zone classification results.
        zone_centroids: {zone: {lat, lon, name}} dict.
        recommendations: DER recommendation dicts.
        data_center_locations: List of DC location dicts for markers.
        transmission_geojson: GeoJSON for transmission lines.
        pnode_data: {coordinates: {}, results: {}} for pnode markers.
        zone_boundaries: GeoJSON for zone boundary polygons.
        backbone_geojson: GeoJSON for backbone transmission lines.
        output_path: Where to save the HTML map.
        map_center: (lat, lon) center for the map.
        map_zoom: Initial zoom level.
        iso_name: Display name for the ISO (used in labels).
        zone_key: Property key for zone code in GeoJSON features.

    Returns:
        Output file path as string.
    """
    import folium
    from folium import plugins

    if output_path is None:
        output_path = Path("output") / "grid_constraint_map.html"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    m = folium.Map(
        location=list(map_center),
        zoom_start=map_zoom,
        tiles="CartoDB positron",
    )

    rec_lookup = {r["zone"]: r for r in recommendations}
    cls_lookup = {}
    for _, row in classification_df.iterrows():
        cls_lookup[row["zone"]] = {
            "classification": row["classification"],
            "transmission_score": row["transmission_score"],
            "generation_score": row["generation_score"],
            "avg_abs_congestion": row.get("avg_abs_congestion", 0),
            "max_congestion": row.get("max_congestion", 0),
        }

    # -- Zone boundary polygons (choropleth) --
    if zone_boundaries and zone_boundaries.get("features"):
        boundary_layer = folium.FeatureGroup(name="Zone Boundaries", show=True)

        for feat in zone_boundaries["features"]:
            zone = feat["properties"].get(zone_key, "")
            info = cls_lookup.get(zone, {})
            feat["properties"]["classification"] = info.get("classification", "unconstrained")
            feat["properties"]["t_score"] = round(info.get("transmission_score", 0), 3)
            feat["properties"]["g_score"] = round(info.get("generation_score", 0), 3)
            feat["properties"]["avg_cong"] = round(info.get("avg_abs_congestion", 0), 2)
            # Ensure NAME field exists for tooltip (HIFLD has it, NYISO uses Zone_Name)
            if "NAME" not in feat["properties"]:
                feat["properties"]["NAME"] = (
                    feat["properties"].get("Zone_Name", "")
                    or feat["properties"].get("Name", "")
                    or zone
                )

        def boundary_style(feature):
            cls = feature["properties"].get("classification", "unconstrained")
            color = CLASS_COLORS.get(cls, "#95a5a6")
            cong = feature["properties"].get("avg_cong", 0)
            opacity = min(0.15 + cong / 20.0, 0.55)
            return {
                "fillColor": color,
                "color": color,
                "weight": 2,
                "fillOpacity": opacity,
                "opacity": 0.7,
            }

        folium.GeoJson(
            zone_boundaries,
            style_function=boundary_style,
            tooltip=folium.GeoJsonTooltip(
                fields=[zone_key, "NAME", "classification", "t_score", "g_score", "avg_cong"],
                aliases=["Zone:", "Utility:", "Classification:", "T-score:", "G-score:", "Avg Congestion:"],
                sticky=True,
            ),
        ).add_to(boundary_layer)

        boundary_layer.add_to(m)
        logger.info(f"Added zone boundary layer with {len(zone_boundaries['features'])} polygons")

    # -- Zone markers --
    zone_layer = folium.FeatureGroup(name="Zone Classifications", show=True)

    for _, row in classification_df.iterrows():
        zone = row["zone"]
        if zone not in zone_centroids:
            continue

        centroid = zone_centroids[zone]
        cls = row["classification"]
        color = CLASS_COLORS.get(cls, "#95a5a6")

        base_radius = 8
        cong_scale = min(row.get("avg_abs_congestion", 0) / 5.0, 3.0)
        radius = base_radius + cong_scale * 6

        popup_lines = [
            f"<b>{zone}</b> ({centroid['name']})",
            f"<b>Classification:</b> {cls.upper()}",
            f"<b>T-score:</b> {row['transmission_score']:.3f}",
            f"<b>G-score:</b> {row['generation_score']:.3f}",
            f"<b>Avg congestion:</b> ${row.get('avg_abs_congestion', 0):.2f}/MWh",
            f"<b>Max congestion:</b> ${row.get('max_congestion', 0):.2f}/MWh",
        ]

        rec = rec_lookup.get(zone)
        if rec:
            popup_lines.append(f"<b>Constrained hours:</b> {rec['annual_constrained_hours']}/yr")
            popup_lines.append("<hr><b>Recommended DERs:</b>")
            popup_lines.append(f"<i>Primary ({rec['primary_recommendation']['category']}):</i>")
            for a in rec["primary_recommendation"]["assets"]:
                popup_lines.append(f"&nbsp;&nbsp;{a['label']}")
            popup_lines.append(f"<i>Secondary ({rec['secondary_recommendation']['category']}):</i>")
            for a in rec["secondary_recommendation"]["assets"]:
                popup_lines.append(f"&nbsp;&nbsp;{a['label']}")

        popup_html = "<br>".join(popup_lines)

        folium.CircleMarker(
            location=[centroid["lat"], centroid["lon"]],
            radius=radius,
            popup=folium.Popup(popup_html, max_width=350),
            tooltip=f"{zone}: {cls}",
            color=color,
            fill=True,
            fill_color=color,
            fill_opacity=0.7,
            weight=2,
        ).add_to(zone_layer)

    zone_layer.add_to(m)

    # -- Data center markers --
    dc_layer = folium.FeatureGroup(name="Data Center Clusters", show=True)

    dc_status_colors = {
        "operational": "#27ae60",
        "proposed": "#3498db",
        "construction": "#e67e22",
    }

    dc_cluster = plugins.MarkerCluster(
        options={
            "maxClusterRadius": 50,
            "disableClusteringAtZoom": 10,
        },
    )

    for dc in data_center_locations:
        status = dc.get("status", "").lower()
        color = dc_status_colors.get(status, "#34495e")
        capacity_mw = dc.get("capacity_mw", 0)

        if capacity_mw > 0:
            radius = min(4 + (capacity_mw / 75) * 3, 10)
        else:
            radius = 5

        popup_parts = [f"<b>{dc.get('name', '')}</b>"]
        popup_parts.append(f"<b>Zone:</b> {dc.get('zone', '')}")
        if status:
            popup_parts.append(f"<b>Status:</b> {status.title()}")
        cap = dc.get("capacity", "")
        if cap:
            popup_parts.append(f"<b>Capacity:</b> {cap}")
        county = dc.get("county", "")
        state_code = dc.get("state_code", "")
        if county or state_code:
            popup_parts.append(f"<b>Location:</b> {county}, {state_code}".rstrip(", "))
        operator = dc.get("operator", "")
        if operator:
            popup_parts.append(f"<b>Operator:</b> {operator}")
        notes = dc.get("notes", "")
        if notes and not operator:
            popup_parts.append(notes)
        popup_html = "<br>".join(popup_parts)

        folium.CircleMarker(
            location=[dc["lat"], dc["lon"]],
            radius=radius,
            popup=folium.Popup(popup_html, max_width=300),
            tooltip=dc.get("name", "Data Center"),
            color=color,
            fill=True,
            fill_color=color,
            fill_opacity=0.7,
            weight=1,
        ).add_to(dc_cluster)

    dc_cluster.add_to(dc_layer)
    dc_layer.add_to(m)

    # -- Transmission lines (live from HIFLD ArcGIS FeatureServer) --
    _EsriTransmissionLayer(
        url=HIFLD_TX_URL,
        where_clause="VOLTAGE >= 230",
    ).add_to(m)

    # -- Backbone Transmission Lines --
    if backbone_geojson and backbone_geojson.get("features"):
        backbone_layer = folium.FeatureGroup(
            name=f"{iso_name} Backbone Lines (345kV+)", show=True
        )

        def backbone_style(feature):
            voltage = (feature.get("properties") or {}).get("VOLTAGE", 0) or 0
            if voltage >= 765:
                return {"color": "#8b0000", "weight": 4, "opacity": 0.9}
            if voltage >= 500:
                return {"color": "#cc0000", "weight": 3, "opacity": 0.85}
            if voltage >= 345:
                return {"color": "#e65c00", "weight": 2, "opacity": 0.75}
            return {"color": "#ff8c00", "weight": 1.5, "opacity": 0.6}

        folium.GeoJson(
            backbone_geojson,
            style_function=backbone_style,
            tooltip=folium.GeoJsonTooltip(
                fields=["NAME", "VOLTAGE", "MILES"],
                aliases=["Line:", "Voltage (kV):", "Miles:"],
                sticky=True,
            ),
        ).add_to(backbone_layer)

        backbone_layer.add_to(m)
        logger.info(
            f"Added backbone layer with "
            f"{len(backbone_geojson['features'])} lines"
        )

    # -- Pnode congestion markers --
    if pnode_data:
        coordinates = pnode_data.get("coordinates", {})
        results = pnode_data.get("results", {})

        if coordinates and results:
            pnode_layer = folium.FeatureGroup(name="Pnode Congestion", show=False)
            marker_cluster = plugins.MarkerCluster(
                options={
                    "maxClusterRadius": 40,
                    "disableClusteringAtZoom": 12,
                },
            )

            for zone, analysis in results.items():
                for pnode in analysis.get("all_scored", []):
                    pname = pnode["pnode_name"]
                    if pname not in coordinates:
                        continue

                    coord = coordinates[pname]
                    if coord.get("source") == "zone_centroid":
                        continue

                    tier = pnode["tier"]
                    color = TIER_COLORS.get(tier, "#95a5a6")
                    score = pnode["severity_score"]

                    lat = coord["lat"] + random.uniform(-0.005, 0.005)
                    lon = coord["lon"] + random.uniform(-0.005, 0.005)
                    radius = 3 + score * 7

                    popup_html = (
                        f"<b>{pname}</b><br>"
                        f"<b>Zone:</b> {zone}<br>"
                        f"<b>Pnode ID:</b> {pnode.get('pnode_id', 'N/A')}<br>"
                        f"<b>Severity:</b> {score:.3f} ({tier})<br>"
                        f"<b>Avg congestion:</b> ${pnode['avg_congestion']:.2f}/MWh<br>"
                        f"<b>Max congestion:</b> ${pnode['max_congestion']:.2f}/MWh"
                    )

                    folium.CircleMarker(
                        location=[lat, lon],
                        radius=radius,
                        popup=folium.Popup(popup_html, max_width=300),
                        tooltip=f"{pname} ({zone}): {tier} [{score:.2f}]",
                        color=color,
                        fill=True,
                        fill_color=color,
                        fill_opacity=0.6,
                        weight=1,
                    ).add_to(marker_cluster)

            marker_cluster.add_to(pnode_layer)
            pnode_layer.add_to(m)
            logger.info(
                f"Added pnode congestion layer with "
                f"{sum(len(a.get('all_scored', [])) for a in results.values())} markers"
            )

    # -- Legend --
    legend_html = f"""
    <div style="position: fixed; bottom: 30px; left: 30px; z-index: 1000;
                background-color: white; border: 2px solid grey; padding: 10px;
                border-radius: 5px; font-size: 13px; opacity: 0.9; max-height: 80vh;
                overflow-y: auto;">
    <b>{iso_name} Constraint Classification</b><br>
    <i style="background: #e74c3c; width: 12px; height: 12px; display: inline-block; border-radius: 50%;"></i> Transmission<br>
    <i style="background: #3498db; width: 12px; height: 12px; display: inline-block; border-radius: 50%;"></i> Generation<br>
    <i style="background: #9b59b6; width: 12px; height: 12px; display: inline-block; border-radius: 50%;"></i> Both<br>
    <i style="background: #2ecc71; width: 12px; height: 12px; display: inline-block; border-radius: 50%;"></i> Unconstrained<br>
    <hr style="margin: 4px 0;">
    <b>Data Centers</b><br>
    <i style="background: #27ae60; width: 12px; height: 12px; display: inline-block; border-radius: 50%;"></i> Operational<br>
    <i style="background: #3498db; width: 12px; height: 12px; display: inline-block; border-radius: 50%;"></i> Proposed<br>
    <i style="background: #e67e22; width: 12px; height: 12px; display: inline-block; border-radius: 50%;"></i> Construction<br>
    <hr style="margin: 4px 0;">
    <b>Transmission Lines</b><br>
    <i style="background: #8b0000; width: 16px; height: 4px; display: inline-block;"></i> 765 kV+<br>
    <i style="background: #cc0000; width: 16px; height: 3px; display: inline-block;"></i> 500 kV<br>
    <i style="background: #e65c00; width: 16px; height: 3px; display: inline-block;"></i> 345 kV<br>
    <i style="background: #ff8c00; width: 16px; height: 3px; display: inline-block;"></i> 230 kV<br>
    <hr style="margin: 4px 0;">
    <b>Pnode Severity Tier</b><br>
    <i style="background: #e74c3c; width: 12px; height: 12px; display: inline-block; border-radius: 50%;"></i> Critical (&ge;0.75)<br>
    <i style="background: #e67e22; width: 12px; height: 12px; display: inline-block; border-radius: 50%;"></i> Elevated (&ge;0.50)<br>
    <i style="background: #f1c40f; width: 12px; height: 12px; display: inline-block; border-radius: 50%;"></i> Moderate (&ge;0.25)<br>
    <i style="background: #27ae60; width: 12px; height: 12px; display: inline-block; border-radius: 50%;"></i> Low (&lt;0.25)<br>
    <br><i>Marker size = severity score</i>
    </div>
    """
    import folium as _folium
    m.get_root().html.add_child(_folium.Element(legend_html))

    folium.LayerControl().add_to(m)

    m.save(str(output_path))
    logger.info(f"Saved interactive map to {output_path}")
    return str(output_path)
