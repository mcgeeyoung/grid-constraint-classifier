"""
Visualization module for grid constraint classification results.

Generates:
  1. Interactive Folium map with zone markers, transmission lines, data centers
  2. Bar chart of transmission vs generation scores by zone
  3. Heatmap of congestion by zone x hour-of-day
  4. Line chart of monthly congestion trends
"""

import json
import logging
from pathlib import Path
from typing import Optional

import random

import numpy as np
import pandas as pd
from jinja2 import Template
from branca.element import MacroElement
import matplotlib
matplotlib.use("Agg")  # Non-interactive backend
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors

logger = logging.getLogger(__name__)

OUTPUT_DIR = Path(__file__).parent.parent / "output"

# Classification → color mapping
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

PJM_STATES_SQL = "1=1"  # No state field available; rely on map viewport for spatial filtering


class _EsriTransmissionLayer(MacroElement):
    """
    MacroElement that injects esri-leaflet and adds a live HIFLD
    transmission FeatureLayer directly to the Folium map.

    Must be added directly to the Map object (not a FeatureGroup) so
    this._parent resolves to the Leaflet map variable.
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

        // Inject toggle into layer control after DOM renders
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
    output_path: Optional[Path] = None,
) -> str:
    """
    Create an interactive Folium map showing constraint classifications.

    Returns the output file path.
    """
    import folium
    from folium import plugins

    if output_path is None:
        output_path = OUTPUT_DIR / "grid_constraint_map.html"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Center on PJM footprint
    m = folium.Map(
        location=[39.5, -78.0],
        zoom_start=6,
        tiles="CartoDB positron",
    )

    # Build recommendation lookup
    rec_lookup = {r["zone"]: r for r in recommendations}

    # Build classification lookup by zone
    cls_lookup = {}
    for _, row in classification_df.iterrows():
        cls_lookup[row["zone"]] = {
            "classification": row["classification"],
            "transmission_score": row["transmission_score"],
            "generation_score": row["generation_score"],
            "avg_abs_congestion": row.get("avg_abs_congestion", 0),
            "max_congestion": row.get("max_congestion", 0),
        }

    # ── Zone boundary polygons (choropleth) ──
    if zone_boundaries and zone_boundaries.get("features"):
        boundary_layer = folium.FeatureGroup(name="Zone Boundaries", show=True)

        # Inject zone classification data into GeoJSON properties
        for feat in zone_boundaries["features"]:
            zone = feat["properties"].get("pjm_zone", "")
            info = cls_lookup.get(zone, {})
            feat["properties"]["classification"] = info.get("classification", "unconstrained")
            feat["properties"]["t_score"] = round(info.get("transmission_score", 0), 3)
            feat["properties"]["g_score"] = round(info.get("generation_score", 0), 3)
            feat["properties"]["avg_cong"] = round(info.get("avg_abs_congestion", 0), 2)

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
                fields=["pjm_zone", "NAME", "classification", "t_score", "g_score", "avg_cong"],
                aliases=["Zone:", "Utility:", "Classification:", "T-score:", "G-score:", "Avg Congestion:"],
                sticky=True,
            ),
        ).add_to(boundary_layer)

        boundary_layer.add_to(m)
        logger.info(f"Added zone boundary layer with {len(zone_boundaries['features'])} polygons")

    # ── Zone markers ──
    zone_layer = folium.FeatureGroup(name="Zone Classifications", show=True)

    for _, row in classification_df.iterrows():
        zone = row["zone"]
        if zone not in zone_centroids:
            continue

        centroid = zone_centroids[zone]
        cls = row["classification"]
        color = CLASS_COLORS.get(cls, "#95a5a6")

        # Scale marker size by congestion magnitude
        base_radius = 8
        cong_scale = min(row.get("avg_abs_congestion", 0) / 5.0, 3.0)
        radius = base_radius + cong_scale * 6

        # Build popup content
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

    # ── Data center markers ──
    dc_layer = folium.FeatureGroup(name="Data Center Clusters", show=True)

    for dc in data_center_locations:
        folium.Marker(
            location=[dc["lat"], dc["lon"]],
            popup=f"<b>{dc['name']}</b><br>Zone: {dc['zone']}<br>{dc['notes']}",
            tooltip=dc["name"],
            icon=folium.Icon(color="darkblue", icon="server", prefix="fa"),
        ).add_to(dc_layer)

    dc_layer.add_to(m)

    # ── Transmission lines (live from HIFLD ArcGIS FeatureServer) ──
    _EsriTransmissionLayer(
        url=HIFLD_TX_URL,
        where_clause="VOLTAGE >= 230",
    ).add_to(m)

    # ── Pnode congestion markers ──
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

                    # Skip centroid fallbacks; only show real geocoded locations
                    if coord.get("source") == "zone_centroid":
                        continue

                    tier = pnode["tier"]
                    color = TIER_COLORS.get(tier, "#95a5a6")
                    score = pnode["severity_score"]

                    # Tiny jitter for co-located pnodes
                    lat = coord["lat"] + random.uniform(-0.005, 0.005)
                    lon = coord["lon"] + random.uniform(-0.005, 0.005)

                    # Radius scaled by severity (3-10 range)
                    radius = 3 + score * 7

                    popup_html = (
                        f"<b>{pname}</b><br>"
                        f"<b>Zone:</b> {zone}<br>"
                        f"<b>Pnode ID:</b> {pnode.get('pnode_id', 'N/A')}<br>"
                        f"<b>Severity:</b> {score:.3f} ({tier})<br>"
                        f"<b>Avg congestion:</b> ${pnode['avg_congestion']:.2f}/MWh<br>"
                        f"<b>Max congestion:</b> ${pnode['max_congestion']:.2f}/MWh"
                    )

                    tooltip_text = f"{pname} ({zone}): {tier} [{score:.2f}]"

                    folium.CircleMarker(
                        location=[lat, lon],
                        radius=radius,
                        popup=folium.Popup(popup_html, max_width=300),
                        tooltip=tooltip_text,
                        color=color,
                        fill=True,
                        fill_color=color,
                        fill_opacity=0.6,
                        weight=1,
                    ).add_to(marker_cluster)

            marker_cluster.add_to(pnode_layer)
            pnode_layer.add_to(m)
            logger.info(f"Added pnode congestion layer with {sum(len(a.get('all_scored', [])) for a in results.values())} markers")

    # ── Legend ──
    legend_html = """
    <div style="position: fixed; bottom: 30px; left: 30px; z-index: 1000;
                background-color: white; border: 2px solid grey; padding: 10px;
                border-radius: 5px; font-size: 13px; opacity: 0.9; max-height: 80vh;
                overflow-y: auto;">
    <b>Constraint Classification</b><br>
    <i style="background: #e74c3c; width: 12px; height: 12px; display: inline-block; border-radius: 50%;"></i> Transmission<br>
    <i style="background: #3498db; width: 12px; height: 12px; display: inline-block; border-radius: 50%;"></i> Generation<br>
    <i style="background: #9b59b6; width: 12px; height: 12px; display: inline-block; border-radius: 50%;"></i> Both<br>
    <i style="background: #2ecc71; width: 12px; height: 12px; display: inline-block; border-radius: 50%;"></i> Unconstrained<br>
    <i style="background: darkblue; width: 12px; height: 12px; display: inline-block;"></i> Data Center<br>
    <hr style="margin: 4px 0;">
    <b>Transmission Lines</b><br>
    <i style="background: #cc0000; width: 16px; height: 3px; display: inline-block;"></i> 500 kV+<br>
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
    m.get_root().html.add_child(folium.Element(legend_html))

    # Layer control
    folium.LayerControl().add_to(m)

    m.save(str(output_path))
    logger.info(f"Saved interactive map to {output_path}")
    return str(output_path)


def create_score_bar_chart(
    classification_df: pd.DataFrame,
    output_path: Optional[Path] = None,
):
    """Bar chart comparing transmission vs generation scores by zone."""
    if output_path is None:
        output_path = OUTPUT_DIR / "score_comparison.png"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    df = classification_df.sort_values("transmission_score", ascending=True)

    fig, ax = plt.subplots(figsize=(12, 8))

    y = np.arange(len(df))
    height = 0.35

    bars_t = ax.barh(y - height/2, df["transmission_score"], height,
                     label="Transmission Score", color="#e74c3c", alpha=0.8)
    bars_g = ax.barh(y + height/2, df["generation_score"], height,
                     label="Generation Score", color="#3498db", alpha=0.8)

    ax.set_yticks(y)
    ax.set_yticklabels(df["zone"])
    ax.set_xlabel("Score (0-1)")
    ax.set_title("PJM Zone Constraint Scores: Transmission vs Generation")
    ax.axvline(x=0.5, color="gray", linestyle="--", alpha=0.5, label="Threshold (0.5)")
    ax.legend(loc="lower right")

    # Color zone labels by classification
    for i, (_, row) in enumerate(df.iterrows()):
        color = CLASS_COLORS.get(row["classification"], "gray")
        ax.get_yticklabels()[i].set_color(color)
        ax.get_yticklabels()[i].set_fontweight("bold")

    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close()
    logger.info(f"Saved score comparison chart to {output_path}")


def create_congestion_heatmap(
    lmp_df: pd.DataFrame,
    output_path: Optional[Path] = None,
):
    """Heatmap of average congestion by zone x hour-of-day."""
    if output_path is None:
        output_path = OUTPUT_DIR / "congestion_heatmap.png"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Filter to zone-level data, exclude RTO aggregates
    rto_aggregates = {"PJM-RTO", "MID-ATL/APS"}
    zone_df = lmp_df[~lmp_df["pnode_name"].isin(rto_aggregates)].copy()

    pivot = zone_df.pivot_table(
        values="congestion_price_da",
        index="pnode_name",
        columns="hour",
        aggfunc=lambda x: x.abs().mean(),
    )

    # Sort by total congestion
    pivot["total"] = pivot.sum(axis=1)
    pivot = pivot.sort_values("total", ascending=True).drop(columns="total")

    fig, ax = plt.subplots(figsize=(14, 8))

    im = ax.imshow(
        pivot.values,
        aspect="auto",
        cmap="YlOrRd",
        interpolation="nearest",
    )

    ax.set_yticks(range(len(pivot.index)))
    ax.set_yticklabels(pivot.index, fontsize=9)
    ax.set_xticks(range(24))
    ax.set_xticklabels([f"{h:02d}" for h in range(24)], fontsize=8)
    ax.set_xlabel("Hour of Day (EPT)")
    ax.set_ylabel("Zone")
    ax.set_title("Average Absolute Congestion Price by Zone and Hour ($/MWh)")

    cbar = plt.colorbar(im, ax=ax, label="$/MWh")

    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close()
    logger.info(f"Saved congestion heatmap to {output_path}")


def create_monthly_trend_chart(
    lmp_df: pd.DataFrame,
    top_n: int = 6,
    output_path: Optional[Path] = None,
):
    """Line chart of monthly congestion trends for top N zones."""
    if output_path is None:
        output_path = OUTPUT_DIR / "monthly_congestion_trends.png"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    rto_aggregates = {"PJM-RTO", "MID-ATL/APS"}
    zone_df = lmp_df[~lmp_df["pnode_name"].isin(rto_aggregates)].copy()

    # Identify top zones by total absolute congestion
    zone_totals = zone_df.groupby("pnode_name")["congestion_price_da"].apply(
        lambda x: x.abs().mean()
    ).nlargest(top_n)

    top_zones = zone_totals.index.tolist()

    fig, ax = plt.subplots(figsize=(12, 6))

    colors = plt.cm.Set1(np.linspace(0, 1, top_n))

    for zone, color in zip(top_zones, colors):
        zdf = zone_df[zone_df["pnode_name"] == zone]
        monthly = zdf.groupby("month")["congestion_price_da"].apply(
            lambda x: x.abs().mean()
        )
        ax.plot(monthly.index, monthly.values, marker="o", label=zone,
                color=color, linewidth=2)

    ax.set_xlabel("Month")
    ax.set_ylabel("Avg |Congestion| ($/MWh)")
    ax.set_title(f"Monthly Congestion Trends: Top {top_n} Zones")
    ax.set_xticks(range(1, 13))
    ax.set_xticklabels(["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                        "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"])
    ax.legend(loc="upper right")
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close()
    logger.info(f"Saved monthly trend chart to {output_path}")
