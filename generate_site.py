"""
Generate GitHub Pages site from grid-constraint-classifier outputs.

Reads:
  output/{iso_id}/classification_summary.json

Produces (single ISO):
  docs/{iso_id}/index.html        (executive summary)
  docs/{iso_id}/dashboard.html    (copy of full interactive dashboard)
  docs/{iso_id}/map.html          (copy of standalone Folium map)

Produces (--iso all):
  docs/index.html                 (multi-ISO landing page)
  docs/{iso_id}/...               (per-ISO pages)

No external dependencies (stdlib only).
"""

import argparse
import html
import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

ROOT = Path(__file__).resolve().parent

CLASSIFICATION_COLORS = {
    "transmission": "#e74c3c",
    "generation": "#3498db",
    "both": "#9b59b6",
    "unconstrained": "#2ecc71",
}

TIER_COLORS = {
    "critical": "#c0392b",
    "elevated": "#e67e22",
    "moderate": "#f1c40f",
    "low": "#27ae60",
}


def load_json(output_dir: Path) -> dict:
    path = output_dir / "classification_summary.json"
    with open(path) as f:
        return json.load(f)


def build_zone_table_rows(data: dict) -> str:
    """Build HTML table rows for all 21 zones."""
    rec_map = {r["zone"]: r for r in data["recommendations"]}
    dc_by_zone = data.get("data_centers", {}).get("by_zone", {})

    rows = []
    for zs in sorted(data["zone_scores"], key=lambda z: -z["transmission_score"]):
        zone = zs["zone"]
        cls = zs["classification"]
        color = CLASSIFICATION_COLORS[cls]
        rec = rec_map.get(zone, {})
        dc_count = dc_by_zone.get(zone, {}).get("total", 0)
        congestion = rec.get("congestion_value_per_mwh", zs.get("avg_abs_congestion", 0))

        rows.append(
            f"<tr>"
            f"<td>{html.escape(zone)}</td>"
            f'<td><span class="cls-badge" style="background:{color}">'
            f"{cls}</span></td>"
            f"<td>{zs['transmission_score']:.3f}</td>"
            f"<td>{zs['generation_score']:.3f}</td>"
            f"<td>${congestion:.2f}</td>"
            f"<td>{zs['congested_hours_pct']:.1%}</td>"
            f"<td>{dc_count}</td>"
            f"</tr>"
        )
    return "\n".join(rows)


def _resolve_dc_classification_site(zone, cls_map, dc_zone_mapping=None):
    """Look up classification for a DC zone, with optional zone translation."""
    direct = cls_map.get(zone)
    if direct:
        return direct
    if not dc_zone_mapping or zone not in dc_zone_mapping:
        return "unconstrained"
    PRIORITY = {"both": 3, "transmission": 2, "generation": 1, "unconstrained": 0}
    worst = "unconstrained"
    for cls_zone in dc_zone_mapping[zone]:
        cls = cls_map.get(cls_zone, "unconstrained")
        if PRIORITY.get(cls, 0) > PRIORITY.get(worst, 0):
            worst = cls
    return worst


def build_growth_pressure(data: dict) -> str:
    """Build growth pressure analysis section."""
    cls_map = {zs["zone"]: zs["classification"] for zs in data["zone_scores"]}
    cls_scores_map = {zs["zone"]: zs for zs in data["zone_scores"]}
    dc_data = data.get("data_centers", {})
    dc_by_zone = dc_data.get("by_zone", {})
    dc_zone_mapping = dc_data.get("dc_zone_to_cls_zones")
    constrained_types = {"transmission", "both"}

    pressure_zones = []
    for zone, zdata in dc_by_zone.items():
        zone_cls = _resolve_dc_classification_site(zone, cls_map, dc_zone_mapping)
        zone_scores = cls_scores_map.get(zone, {})
        proposed = zdata.get("proposed", 0)
        if zone_cls in constrained_types and proposed >= 5:
            pressure_zones.append({
                "zone": zone,
                "classification": zone_cls,
                "t_score": zone_scores.get("transmission_score", 0),
                "proposed": proposed,
                "total": zdata.get("total", 0),
                "operational": zdata.get("operational", 0),
                "estimated_mw": zdata.get("estimated_mw", 0),
            })

    if not pressure_zones:
        return ""

    items = []
    for pz in sorted(pressure_zones, key=lambda x: -x["proposed"]):
        cls_color = CLASSIFICATION_COLORS.get(pz["classification"], "#888")
        items.append(
            f'<div class="pressure-card">'
            f'<div class="pressure-zone">{html.escape(pz["zone"])}'
            f' <span class="cls-badge" style="background:{cls_color}">'
            f'{pz["classification"]}</span></div>'
            f'<div class="pressure-stats">'
            f'<span><b>{pz["proposed"]}</b> proposed DCs</span>'
            f'<span><b>{pz["total"]}</b> total DCs</span>'
            f'<span><b>{pz["estimated_mw"]:,.0f}</b> MW est. capacity</span>'
            f'<span>T-score: <b>{pz["t_score"]:.3f}</b></span>'
            f'</div>'
            f'</div>'
        )

    return f"""
    <div class="pressure-section">
      <h3>Growth Pressure Zones</h3>
      <p class="pressure-desc">Zones that are transmission-constrained AND have significant
      proposed data center capacity represent the highest-priority areas for DER deployment.
      New load in these zones will worsen existing congestion, increasing costs for all
      ratepayers and creating reliability risks.</p>
      <div class="pressure-grid">{"".join(items)}</div>
    </div>
    """


def build_pnode_drilldown(data: dict) -> str:
    """Build the pnode drilldown section with per-zone hotspot tables."""
    pnode_drilldown = data.get("pnode_drilldown", {})
    if not pnode_drilldown:
        return ""

    cls_map = {zs["zone"]: zs for zs in data["zone_scores"]}

    # Sort zones by number of critical+elevated pnodes descending
    def zone_severity(zone):
        td = pnode_drilldown[zone].get("tier_distribution", {})
        return (td.get("critical", 0) * 10 + td.get("elevated", 0),
                pnode_drilldown[zone].get("total_pnodes", 0))

    sorted_zones = sorted(pnode_drilldown.keys(), key=zone_severity, reverse=True)

    zone_cards = []
    for zone in sorted_zones:
        zd = pnode_drilldown[zone]
        td = zd.get("tier_distribution", {})
        hotspots = zd.get("hotspots", [])
        total = zd.get("total_pnodes", 0)
        zs = cls_map.get(zone, {})
        cls = zs.get("classification", "unconstrained")
        cls_color = CLASSIFICATION_COLORS.get(cls, "#888")

        # Tier distribution badges
        tier_badges = []
        for tier in ("critical", "elevated", "moderate", "low"):
            count = td.get(tier, 0)
            if count > 0:
                color = TIER_COLORS[tier]
                tier_badges.append(
                    f'<span class="tier-badge" style="background:{color}">'
                    f'{tier}: {count}</span>'
                )
        badges_html = " ".join(tier_badges)

        # Top 3 hotspot rows
        hotspot_rows = []
        for hs in hotspots[:3]:
            tier = hs.get("tier", "low")
            tier_color = TIER_COLORS.get(tier, "#27ae60")
            hotspot_rows.append(
                f"<tr>"
                f"<td>{html.escape(str(hs.get('pnode_name', '')))}</td>"
                f"<td>{hs.get('severity_score', 0):.4f}</td>"
                f"<td>${hs.get('avg_congestion', 0):.2f}</td>"
                f"<td>${hs.get('max_congestion', 0):.2f}</td>"
                f"<td>{hs.get('congested_hours_pct', 0):.1%}</td>"
                f'<td><span class="tier-badge" style="background:{tier_color}">'
                f'{tier}</span></td>'
                f"</tr>"
            )
        rows_html = "\n".join(hotspot_rows)

        zone_cards.append(f"""
        <div class="pnode-zone-card">
          <div class="pnode-zone-header">
            <span class="pnode-zone-name">{html.escape(zone)}</span>
            <span class="cls-badge" style="background:{cls_color}">{cls}</span>
            <span class="pnode-zone-count">{total} pnodes</span>
          </div>
          <div class="pnode-tier-row">{badges_html}</div>
          <table class="pnode-table">
            <thead>
              <tr>
                <th>Pnode</th>
                <th>Severity</th>
                <th>Avg $/MWh</th>
                <th>Max $/MWh</th>
                <th>Constrained %</th>
                <th>Tier</th>
              </tr>
            </thead>
            <tbody>{rows_html}</tbody>
          </table>
        </div>
        """)

    return "\n".join(zone_cards)


def build_executive_summary(data: dict, iso_name: str = "PJM") -> str:
    """Generate the full executive summary HTML page."""
    meta = data["metadata"]
    iso_id = meta.get("iso_id", "pjm")
    dist = data.get("distribution", {})
    dc = data.get("data_centers", {})
    pnode_drilldown = data.get("pnode_drilldown", {})
    now = datetime.now().strftime("%Y-%m-%d")
    year = meta["year"]

    # Count constrained zones
    constrained_count = dist.get("transmission", 0) + dist.get("both", 0) + dist.get("generation", 0)

    # Find most constrained zone
    zone_scores = sorted(data["zone_scores"], key=lambda z: -z["transmission_score"])
    top_zone = zone_scores[0]

    # Data center stats
    dc_total = dc.get("total_count", 0)
    dc_mw = dc.get("total_estimated_mw", 0)
    dc_proposed = dc.get("status_totals", {}).get("proposed", 0)

    # Pnode stats
    total_pnodes = sum(pd.get("total_pnodes", 0) for pd in pnode_drilldown.values())
    total_critical = sum(
        pd.get("tier_distribution", {}).get("critical", 0)
        for pd in pnode_drilldown.values()
    )

    # Find top zone congestion from recommendations
    rec_map = {r["zone"]: r for r in data["recommendations"]}
    top_congestion = rec_map.get(top_zone["zone"], {}).get(
        "congestion_value_per_mwh", top_zone.get("avg_abs_congestion", 0)
    )

    # GIS metadata (PJM-specific fields, optional for other ISOs)
    backbone_lines = meta.get("pjm_backbone_lines", 0)
    zone_boundaries = meta.get("pjm_zone_boundaries", 0)

    zone_table_rows = build_zone_table_rows(data)
    growth_pressure = build_growth_pressure(data)
    pnode_section = build_pnode_drilldown(data)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{iso_name} Grid Constraint Classifier</title>
<style>
*, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  background: #f5f6fa;
  color: #2c3e50;
  line-height: 1.6;
}}

/* Header */
.header {{
  background: linear-gradient(135deg, #1a252f, #2c3e50);
  color: #fff;
  padding: 3rem 2rem 2.5rem;
  text-align: center;
}}
.header h1 {{
  font-size: 2rem;
  font-weight: 700;
  margin-bottom: 0.5rem;
}}
.header .subtitle {{
  color: #bdc3c7;
  font-size: 1rem;
  margin-bottom: 0.25rem;
}}
.header .context {{
  color: #7f8c8d;
  font-size: 0.85rem;
}}

/* Container */
.container {{
  max-width: 1200px;
  margin: 0 auto;
  padding: 2rem;
}}

/* Section */
.section {{
  margin-bottom: 2.5rem;
}}
.section-title {{
  font-size: 1.35rem;
  font-weight: 700;
  color: #2c3e50;
  margin-bottom: 1rem;
  padding-bottom: 0.5rem;
  border-bottom: 2px solid #3498db;
}}

/* Stat Cards */
.stat-cards {{
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 1rem;
  margin-bottom: 2rem;
}}
.stat-card {{
  background: #fff;
  border-radius: 8px;
  padding: 1.5rem;
  box-shadow: 0 2px 8px rgba(0,0,0,0.08);
  text-align: center;
}}
.stat-card.highlight {{
  border-left: 4px solid #e74c3c;
}}
.stat-value {{
  font-size: 1.75rem;
  font-weight: 700;
  color: #2c3e50;
}}
.stat-label {{
  font-size: 0.8rem;
  color: #7f8c8d;
  margin-top: 0.25rem;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}}
.stat-detail {{
  font-size: 0.78rem;
  color: #95a5a6;
  margin-top: 0.35rem;
}}

/* Classification badges */
.cls-badge {{
  display: inline-block;
  padding: 0.15em 0.55em;
  border-radius: 4px;
  color: #fff;
  font-size: 0.78rem;
  font-weight: 600;
  white-space: nowrap;
}}

/* What This Tool Does */
.feature-list {{
  background: #fff;
  border-radius: 8px;
  padding: 1.5rem 2rem;
  box-shadow: 0 2px 8px rgba(0,0,0,0.08);
}}
.feature-list ul {{
  list-style: none;
  padding: 0;
}}
.feature-list li {{
  padding: 0.5rem 0;
  border-bottom: 1px solid #ecf0f1;
  font-size: 0.9rem;
  display: flex;
  align-items: flex-start;
  gap: 0.75rem;
}}
.feature-list li:last-child {{
  border-bottom: none;
}}
.feature-list .bullet {{
  flex-shrink: 0;
  width: 8px;
  height: 8px;
  background: #3498db;
  border-radius: 50%;
  margin-top: 0.5rem;
}}

/* Pipeline */
.pipeline {{
  display: flex;
  flex-wrap: wrap;
  gap: 0;
  align-items: stretch;
}}
.pipeline-step {{
  flex: 1 1 180px;
  background: #fff;
  border-radius: 8px;
  padding: 1.25rem;
  box-shadow: 0 2px 8px rgba(0,0,0,0.08);
  position: relative;
  min-width: 180px;
}}
.pipeline-step::after {{
  content: "";
  position: absolute;
  right: -12px;
  top: 50%;
  transform: translateY(-50%);
  width: 0;
  height: 0;
  border-top: 12px solid transparent;
  border-bottom: 12px solid transparent;
  border-left: 12px solid #3498db;
  z-index: 1;
}}
.pipeline-step:last-child::after {{
  display: none;
}}
.pipeline-phase {{
  font-size: 0.7rem;
  font-weight: 700;
  text-transform: uppercase;
  color: #3498db;
  letter-spacing: 0.5px;
  margin-bottom: 0.25rem;
}}
.pipeline-name {{
  font-size: 0.9rem;
  font-weight: 600;
  color: #2c3e50;
  margin-bottom: 0.35rem;
}}
.pipeline-desc {{
  font-size: 0.78rem;
  color: #7f8c8d;
}}

/* Table */
.table-wrap {{
  background: #fff;
  border-radius: 8px;
  overflow-x: auto;
  box-shadow: 0 2px 8px rgba(0,0,0,0.08);
}}
table.zone-table {{
  width: 100%;
  border-collapse: collapse;
  font-size: 0.85rem;
}}
table.zone-table th {{
  background: #34495e;
  color: #fff;
  padding: 0.75rem;
  text-align: left;
  font-weight: 600;
  white-space: nowrap;
}}
table.zone-table td {{
  padding: 0.65rem 0.75rem;
  border-bottom: 1px solid #ecf0f1;
}}
table.zone-table tbody tr:hover {{
  background: #f8f9fa;
}}

/* Growth Pressure */
.pressure-section {{
  background: #fef9e7;
  border: 2px solid #f1c40f;
  border-radius: 8px;
  padding: 1.5rem;
}}
.pressure-section h3 {{
  font-size: 1.1rem;
  color: #7d6608;
  margin-bottom: 0.5rem;
}}
.pressure-desc {{
  font-size: 0.85rem;
  color: #7d6608;
  margin-bottom: 1rem;
}}
.pressure-grid {{
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 1rem;
}}
.pressure-card {{
  background: #fff;
  border-radius: 6px;
  padding: 1rem 1.25rem;
  border: 1px solid #f1c40f;
}}
.pressure-zone {{
  font-size: 1rem;
  font-weight: 700;
  color: #2c3e50;
  margin-bottom: 0.5rem;
}}
.pressure-stats {{
  display: flex;
  flex-wrap: wrap;
  gap: 0.75rem;
  font-size: 0.82rem;
  color: #555;
}}

/* CTA Button */
.cta-section {{
  text-align: center;
  padding: 2rem;
}}
.cta-btn {{
  display: inline-block;
  padding: 1rem 2.5rem;
  background: linear-gradient(135deg, #2c3e50, #34495e);
  color: #fff;
  text-decoration: none;
  border-radius: 8px;
  font-size: 1.1rem;
  font-weight: 600;
  transition: transform 0.15s, box-shadow 0.15s;
  box-shadow: 0 4px 12px rgba(0,0,0,0.15);
}}
.cta-btn:hover {{
  transform: translateY(-2px);
  box-shadow: 0 6px 20px rgba(0,0,0,0.2);
}}
.cta-sub {{
  font-size: 0.82rem;
  color: #7f8c8d;
  margin-top: 0.75rem;
}}

/* Methodology */
.method-grid {{
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1rem;
}}
.method-card {{
  background: #fff;
  border-radius: 8px;
  padding: 1.25rem;
  box-shadow: 0 2px 8px rgba(0,0,0,0.08);
}}
.method-card h4 {{
  font-size: 0.9rem;
  color: #34495e;
  margin-bottom: 0.5rem;
}}
.method-card p {{
  font-size: 0.82rem;
  color: #666;
  margin-bottom: 0.5rem;
}}
.method-table {{
  width: 100%;
  font-size: 0.8rem;
  border-collapse: collapse;
}}
.method-table td {{
  padding: 0.3rem 0.4rem;
  border-bottom: 1px solid #ecf0f1;
}}
.method-table td:last-child {{
  text-align: right;
  font-weight: 600;
}}

/* Pnode Drilldown */
.pnode-zone-card {{
  background: #fff;
  border-radius: 8px;
  padding: 1.25rem;
  box-shadow: 0 2px 8px rgba(0,0,0,0.08);
  margin-bottom: 1rem;
}}
.pnode-zone-header {{
  display: flex;
  align-items: center;
  gap: 0.75rem;
  margin-bottom: 0.5rem;
}}
.pnode-zone-name {{
  font-size: 1.1rem;
  font-weight: 700;
  color: #2c3e50;
}}
.pnode-zone-count {{
  font-size: 0.82rem;
  color: #7f8c8d;
}}
.pnode-tier-row {{
  display: flex;
  gap: 0.5rem;
  flex-wrap: wrap;
  margin-bottom: 0.75rem;
}}
.tier-badge {{
  display: inline-block;
  padding: 0.15em 0.55em;
  border-radius: 4px;
  color: #fff;
  font-size: 0.75rem;
  font-weight: 600;
  white-space: nowrap;
}}
table.pnode-table {{
  width: 100%;
  border-collapse: collapse;
  font-size: 0.82rem;
}}
table.pnode-table th {{
  background: #5d6d7e;
  color: #fff;
  padding: 0.5rem 0.6rem;
  text-align: left;
  font-weight: 600;
  font-size: 0.78rem;
}}
table.pnode-table td {{
  padding: 0.45rem 0.6rem;
  border-bottom: 1px solid #ecf0f1;
}}
table.pnode-table tbody tr:hover {{
  background: #f0f4f8;
}}

/* Footer */
.footer {{
  text-align: center;
  padding: 2rem;
  color: #95a5a6;
  font-size: 0.78rem;
  border-top: 1px solid #e0e0e0;
  margin-top: 1rem;
}}

/* Responsive */
@media (max-width: 768px) {{
  .container {{ padding: 1rem; }}
  .header {{ padding: 2rem 1rem; }}
  .header h1 {{ font-size: 1.5rem; }}
  .stat-cards {{ grid-template-columns: 1fr 1fr; }}
  .pipeline {{ flex-direction: column; }}
  .pipeline-step::after {{ display: none; }}
  .method-grid {{ grid-template-columns: 1fr; }}
}}
</style>
</head>
<body>

<div class="header">
  <h1>{iso_name} Grid Constraint Classifier</h1>
  <div class="subtitle">Identifying where the grid is congested and where DERs can help</div>
  <div class="context">Built by WattCarbon | Data: {iso_name} {year}</div>
</div>

<div class="container">

  <!-- What This Tool Does -->
  <div class="section">
    <h2 class="section-title">What This Tool Does</h2>
    <div class="feature-list">
      <ul>
        <li><span class="bullet"></span>
          <span>Pulls <b>{meta['total_zone_lmp_rows']:,}</b> hourly LMP data points from
          {iso_name} ({year}), decomposing each into congestion, energy, and loss components</span></li>
        <li><span class="bullet"></span>
          <span>Classifies all <b>{meta['zones_analyzed']}</b> {iso_name} pricing zones as
          transmission-constrained, generation-constrained, both, or unconstrained using weighted
          multi-factor scoring</span></li>
        {"" if not total_pnodes else f'''<li><span class="bullet"></span>
          <span>Drills down to <b>{total_pnodes}</b> individual pricing nodes (pnodes) with
          severity scoring and 12x24 constraint loadshapes showing monthly/hourly congestion patterns</span></li>'''}
        {"" if not dc_total else f'''<li><span class="bullet"></span>
          <span>Scrapes <b>{dc_total:,}</b> data center records from interconnection queues and
          maps them to {iso_name} zones, identifying growth pressure areas</span></li>'''}
        {"" if not backbone_lines else f'''<li><span class="bullet"></span>
          <span>Overlays GIS backbone transmission lines (<b>{backbone_lines}</b>
          lines, 345-765kV) and official zone boundaries on an interactive map</span></li>'''}
        <li><span class="bullet"></span>
          <span>Generates DER deployment recommendations per zone, aligned with WattCarbon WEATS
          asset categories (dispatchable, consistent, variable)</span></li>
      </ul>
    </div>
  </div>

  <!-- Key Findings -->
  <div class="section">
    <h2 class="section-title">Key Findings</h2>
    <div class="stat-cards">
      <div class="stat-card">
        <div class="stat-value">{meta['zones_analyzed']}</div>
        <div class="stat-label">Zones Analyzed</div>
        <div class="stat-detail">{constrained_count} constrained ({dist.get('transmission', 0)} transmission,
        {dist.get('both', 0)} both, {dist.get('generation', 0)} generation)</div>
      </div>
      <div class="stat-card highlight">
        <div class="stat-value">{html.escape(top_zone['zone'])}</div>
        <div class="stat-label">Most Constrained Zone</div>
        <div class="stat-detail">T-score {top_zone['transmission_score']:.3f},
        ${top_congestion:.2f}/MWh avg congestion</div>
      </div>
      {"" if not dc_total else f'''<div class="stat-card">
        <div class="stat-value">{dc_total:,}</div>
        <div class="stat-label">{iso_name} Data Centers</div>
        <div class="stat-detail">{dc_mw:,.0f} MW estimated capacity,
        {dc_proposed} proposed</div>
      </div>'''}
      {"" if not total_pnodes else f'''<div class="stat-card">
        <div class="stat-value">{total_pnodes}</div>
        <div class="stat-label">Pnodes Analyzed</div>
        <div class="stat-detail">{total_critical} critical hotspots across
        {len(pnode_drilldown)} zones</div>
      </div>'''}
      {"" if not backbone_lines else f'''<div class="stat-card">
        <div class="stat-value">{backbone_lines}</div>
        <div class="stat-label">Transmission Lines Mapped</div>
        <div class="stat-detail">345-765kV backbone, {zone_boundaries} zone boundaries</div>
      </div>'''}
    </div>
  </div>

  <!-- How It Works -->
  <div class="section">
    <h2 class="section-title">How It Works</h2>
    <div class="pipeline">
      <div class="pipeline-step">
        <div class="pipeline-phase">Phase 1</div>
        <div class="pipeline-name">Data Acquisition</div>
        <div class="pipeline-desc">{iso_name} hourly LMPs + HIFLD transmission lines and zone boundaries</div>
      </div>
      <div class="pipeline-step">
        <div class="pipeline-phase">Phase 1.5</div>
        <div class="pipeline-name">Data Center Scrape</div>
        <div class="pipeline-desc">Interconnection queue scraping, geocoding, and zone mapping{f" for {dc_total:,} facilities" if dc_total else ""}</div>
      </div>
      <div class="pipeline-step">
        <div class="pipeline-phase">Phase 2</div>
        <div class="pipeline-name">Constraint Classification</div>
        <div class="pipeline-desc">Weighted scoring across congestion ratio, volatility, constrained hours, and peak/off-peak patterns</div>
      </div>
      <div class="pipeline-step">
        <div class="pipeline-phase">Phase 2.5</div>
        <div class="pipeline-name">Pnode Drill-Down</div>
        <div class="pipeline-desc">{total_pnodes} individual nodes with severity tiers and 12x24 constraint loadshapes</div>
      </div>
      <div class="pipeline-step">
        <div class="pipeline-phase">Phase 3</div>
        <div class="pipeline-name">DER Recommendations</div>
        <div class="pipeline-desc">Dispatchable, consistent, and variable DER strategies mapped to WEATS EAC categories</div>
      </div>
      <div class="pipeline-step">
        <div class="pipeline-phase">Phase 4</div>
        <div class="pipeline-name">Visualization</div>
        <div class="pipeline-desc">Interactive Folium map with zone boundaries, transmission lines, pnode markers, and data center overlay</div>
      </div>
    </div>
  </div>

  <!-- Zone Classification Table -->
  <div class="section">
    <h2 class="section-title">Zone Classifications</h2>
    <div class="table-wrap">
      <table class="zone-table">
        <thead>
          <tr>
            <th>Zone</th>
            <th>Classification</th>
            <th>T-Score</th>
            <th>G-Score</th>
            <th>Avg Congestion</th>
            <th>Constrained Hrs</th>
            <th>Data Centers</th>
          </tr>
        </thead>
        <tbody>
          {zone_table_rows}
        </tbody>
      </table>
    </div>
  </div>

  <!-- Growth Pressure -->
  <div class="section">
    <h2 class="section-title">Growth Pressure Analysis</h2>
    {growth_pressure}
  </div>

  <!-- Pnode Drilldown -->
  <div class="section">
    <h2 class="section-title">Pnode Congestion Hotspots</h2>
    <p style="font-size:0.85rem;color:#7f8c8d;margin-bottom:1rem;">Top 3 congestion
    hotspots per constrained zone, ranked by severity score. Full pnode tables with
    12x24 loadshapes are available in the interactive dashboard.</p>
    {pnode_section}
  </div>

  <!-- CTA: View Dashboard -->
  <div class="cta-section">
    <a href="dashboard.html" class="cta-btn">View Full Interactive Dashboard</a>
    <div class="cta-sub">Interactive map, sortable tables, congestion heatmaps, pnode loadshapes, and DER recommendations</div>
    <div style="margin-top:1rem">
      <a href="map.html" style="color:#3498db;font-size:0.9rem">Or view the standalone constraint map</a>
    </div>
  </div>

  <!-- Methodology -->
  <div class="section">
    <h2 class="section-title">Methodology</h2>
    <div class="method-grid">
      <div class="method-card">
        <h4>Transmission Score</h4>
        <p>Weighted composite of congestion-based metrics:</p>
        <table class="method-table">
          <tr><td>Congestion Ratio</td><td>|congestion| / |LMP|</td><td>30%</td></tr>
          <tr><td>Congestion Volatility</td><td>Std dev of congestion prices</td><td>25%</td></tr>
          <tr><td>Congested Hours %</td><td>Hours with |congestion| > $2/MWh</td><td>25%</td></tr>
          <tr><td>Peak/Off-Peak Ratio</td><td>Peak vs off-peak congestion</td><td>20%</td></tr>
        </table>
      </div>
      <div class="method-card">
        <h4>Generation Score</h4>
        <p>Weighted composite of energy-price metrics:</p>
        <table class="method-table">
          <tr><td>Energy Deviation</td><td>Zone vs system energy price</td><td>35%</td></tr>
          <tr><td>Energy Volatility</td><td>Energy price std/mean</td><td>30%</td></tr>
          <tr><td>Loss Component</td><td>Marginal loss ratio</td><td>20%</td></tr>
          <tr><td>High Energy Hours %</td><td>Hours > avg + $3/MWh</td><td>15%</td></tr>
        </table>
      </div>
      <div class="method-card">
        <h4>Classification Threshold</h4>
        <p>Zones are classified based on a 0.5 threshold for each score.</p>
        <p>
          <span class="cls-badge" style="background:#e74c3c">transmission</span> T &ge; 0.5, G &lt; 0.5 &nbsp;
          <span class="cls-badge" style="background:#3498db">generation</span> T &lt; 0.5, G &ge; 0.5 &nbsp;
          <span class="cls-badge" style="background:#9b59b6">both</span> T &ge; 0.5, G &ge; 0.5 &nbsp;
          <span class="cls-badge" style="background:#2ecc71">unconstrained</span> T &lt; 0.5, G &lt; 0.5
        </p>
      </div>
      <div class="method-card">
        <h4>Data Sources</h4>
        <p>
          <b>LMP data:</b> {iso_name} day-ahead hourly LMPs ({year})<br>
          <b>Transmission:</b> HIFLD transmission line data{" + PJM GIS backbone (345-765kV)" if iso_id == "pjm" else ""}<br>
          <b>Zone boundaries:</b> {"PJM official zone boundary GIS data" if iso_id == "pjm" else "HIFLD territory boundaries"}<br>
          {"<b>Data centers:</b> interconnection queue listings<br>" if dc_total else ""}
          {"<b>Pnode coordinates:</b> pnode metadata + geocoding" if total_pnodes else ""}
        </p>
      </div>
    </div>
  </div>

</div>

<div class="footer">
  Generated {now} | {iso_name} Grid Constraint Classifier |
  Data: {iso_name} day-ahead hourly LMPs ({year})
</div>

</body>
</html>"""


def generate_iso_site(iso_id: str) -> Optional[dict]:
    """Generate site for a single ISO. Returns summary data or None if no data."""
    output_dir = ROOT / "output" / iso_id
    docs_dir = ROOT / "docs" / iso_id

    if not (output_dir / "classification_summary.json").exists():
        print(f"  {iso_id}: no classification_summary.json, skipping")
        return None

    print(f"  {iso_id}: loading classification summary...")
    data = load_json(output_dir)
    iso_name = data.get("metadata", {}).get("iso_name", iso_id.upper())

    print(f"  {iso_id}: generating executive summary...")
    summary_html = build_executive_summary(data, iso_name=iso_name)

    docs_dir.mkdir(parents=True, exist_ok=True)

    # Write executive summary
    index_path = docs_dir / "index.html"
    with open(index_path, "w") as f:
        f.write(summary_html)
    size_kb = index_path.stat().st_size / 1024
    print(f"  {iso_id}: docs/{iso_id}/index.html ({size_kb:.0f} KB)")

    # Copy dashboard
    dashboard_src = output_dir / "dashboard.html"
    dashboard_dst = docs_dir / "dashboard.html"
    if dashboard_src.exists():
        shutil.copy2(dashboard_src, dashboard_dst)
        size_mb = dashboard_dst.stat().st_size / 1024 / 1024
        print(f"  {iso_id}: docs/{iso_id}/dashboard.html ({size_mb:.1f} MB)")

    # Copy map
    map_src = output_dir / "grid_constraint_map.html"
    map_dst = docs_dir / "map.html"
    if map_src.exists():
        shutil.copy2(map_src, map_dst)
        size_mb = map_dst.stat().st_size / 1024 / 1024
        print(f"  {iso_id}: docs/{iso_id}/map.html ({size_mb:.1f} MB)")

    return data


def build_landing_page(iso_summaries: Dict[str, dict]) -> str:
    """Build the multi-ISO landing page with cards linking to each ISO."""
    now = datetime.now().strftime("%Y-%m-%d")

    iso_cards = []
    for iso_id, data in sorted(iso_summaries.items()):
        meta = data["metadata"]
        iso_name = meta.get("iso_name", iso_id.upper())
        year = meta["year"]
        dist = data.get("distribution", {})
        zones = meta.get("zones_analyzed", 0)

        # Classification counts
        t_count = dist.get("transmission", 0)
        g_count = dist.get("generation", 0)
        b_count = dist.get("both", 0)
        u_count = dist.get("unconstrained", 0)
        constrained = t_count + g_count + b_count

        # Top constrained zone
        zone_scores = sorted(data.get("zone_scores", []), key=lambda z: -z["transmission_score"])
        top_zone = zone_scores[0]["zone"] if zone_scores else "N/A"
        top_t_score = zone_scores[0]["transmission_score"] if zone_scores else 0

        # Badge HTML
        badges = []
        if t_count:
            badges.append(f'<span class="badge" style="background:#e74c3c">T: {t_count}</span>')
        if g_count:
            badges.append(f'<span class="badge" style="background:#3498db">G: {g_count}</span>')
        if b_count:
            badges.append(f'<span class="badge" style="background:#9b59b6">B: {b_count}</span>')
        if u_count:
            badges.append(f'<span class="badge" style="background:#2ecc71">U: {u_count}</span>')
        badge_html = " ".join(badges)

        iso_cards.append(f"""
        <a href="{iso_id}/index.html" class="iso-card">
          <div class="iso-card-header">
            <span class="iso-card-name">{html.escape(iso_name)}</span>
            <span class="iso-card-id">{iso_id.upper()}</span>
          </div>
          <div class="iso-card-stats">
            <div class="iso-stat"><span class="iso-stat-val">{zones}</span> zones</div>
            <div class="iso-stat"><span class="iso-stat-val">{constrained}</span> constrained</div>
            <div class="iso-stat"><span class="iso-stat-val">{meta['total_zone_lmp_rows']:,}</span> LMP rows</div>
          </div>
          <div class="iso-card-badges">{badge_html}</div>
          <div class="iso-card-top">Top: <b>{html.escape(top_zone)}</b> (T={top_t_score:.3f})</div>
        </a>
        """)

    cards_html = "\n".join(iso_cards)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Grid Constraint Classifier - Multi-ISO</title>
<style>
*, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  background: #f5f6fa;
  color: #2c3e50;
  line-height: 1.6;
}}
.header {{
  background: linear-gradient(135deg, #1a252f, #2c3e50);
  color: #fff;
  padding: 3rem 2rem 2.5rem;
  text-align: center;
}}
.header h1 {{ font-size: 2rem; font-weight: 700; margin-bottom: 0.5rem; }}
.header .subtitle {{ color: #bdc3c7; font-size: 1rem; margin-bottom: 0.25rem; }}
.header .context {{ color: #7f8c8d; font-size: 0.85rem; }}
.container {{ max-width: 1200px; margin: 0 auto; padding: 2rem; }}
.iso-grid {{
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 1.5rem;
  margin-top: 1.5rem;
}}
.iso-card {{
  background: #fff;
  border-radius: 10px;
  padding: 1.5rem;
  box-shadow: 0 2px 12px rgba(0,0,0,0.08);
  text-decoration: none;
  color: inherit;
  transition: transform 0.15s, box-shadow 0.15s;
  display: block;
}}
.iso-card:hover {{
  transform: translateY(-3px);
  box-shadow: 0 6px 20px rgba(0,0,0,0.15);
}}
.iso-card-header {{
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 0.75rem;
}}
.iso-card-name {{ font-size: 1.15rem; font-weight: 700; color: #2c3e50; }}
.iso-card-id {{
  background: #34495e;
  color: #fff;
  padding: 0.15em 0.5em;
  border-radius: 4px;
  font-size: 0.75rem;
  font-weight: 600;
}}
.iso-card-stats {{
  display: flex;
  gap: 1rem;
  margin-bottom: 0.75rem;
}}
.iso-stat {{
  font-size: 0.82rem;
  color: #7f8c8d;
}}
.iso-stat-val {{
  font-weight: 700;
  color: #2c3e50;
  font-size: 1rem;
}}
.iso-card-badges {{
  display: flex;
  gap: 0.4rem;
  flex-wrap: wrap;
  margin-bottom: 0.5rem;
}}
.badge {{
  display: inline-block;
  padding: 0.15em 0.5em;
  border-radius: 4px;
  color: #fff;
  font-size: 0.72rem;
  font-weight: 600;
}}
.iso-card-top {{
  font-size: 0.82rem;
  color: #555;
}}
.section-title {{
  font-size: 1.35rem;
  font-weight: 700;
  color: #2c3e50;
  margin-bottom: 0.5rem;
  padding-bottom: 0.5rem;
  border-bottom: 2px solid #3498db;
}}
.footer {{
  text-align: center;
  padding: 2rem;
  color: #95a5a6;
  font-size: 0.78rem;
  border-top: 1px solid #e0e0e0;
  margin-top: 2rem;
}}
@media (max-width: 768px) {{
  .container {{ padding: 1rem; }}
  .header {{ padding: 2rem 1rem; }}
  .header h1 {{ font-size: 1.5rem; }}
  .iso-grid {{ grid-template-columns: 1fr; }}
}}
</style>
</head>
<body>
<div class="header">
  <h1>Grid Constraint Classifier</h1>
  <div class="subtitle">Multi-ISO grid constraint analysis with DER deployment recommendations</div>
  <div class="context">Built by WattCarbon | {len(iso_summaries)} ISOs analyzed</div>
</div>
<div class="container">
  <h2 class="section-title">Select an ISO/RTO</h2>
  <div class="iso-grid">
    {cards_html}
  </div>
</div>
<div class="footer">
  Generated {now} | Grid Constraint Classifier |
  Covering {len(iso_summaries)} ISOs across the US power grid
</div>
</body>
</html>"""


def main():
    parser = argparse.ArgumentParser(description="Generate GitHub Pages site for an ISO")
    parser.add_argument(
        "--iso", type=str, default="pjm",
        help='ISO identifier (default: pjm). Use "all" to generate for all ISOs with data.',
    )
    args = parser.parse_args()

    iso_id = args.iso.lower()
    docs_root = ROOT / "docs"
    docs_root.mkdir(exist_ok=True)

    if iso_id == "all":
        # Find all ISOs that have output data
        output_root = ROOT / "output"
        iso_summaries = {}
        for iso_dir in sorted(output_root.iterdir()):
            if iso_dir.is_dir() and (iso_dir / "classification_summary.json").exists():
                data = generate_iso_site(iso_dir.name)
                if data:
                    iso_summaries[iso_dir.name] = data

        if iso_summaries:
            # Build landing page
            print("\nGenerating multi-ISO landing page...")
            landing_html = build_landing_page(iso_summaries)
            landing_path = docs_root / "index.html"
            with open(landing_path, "w") as f:
                f.write(landing_html)
            size_kb = landing_path.stat().st_size / 1024
            print(f"  docs/index.html ({size_kb:.0f} KB)")

        print(f"\nDone. Site ready in docs/ with {len(iso_summaries)} ISOs.")
    else:
        data = generate_iso_site(iso_id)
        if data:
            print(f"\nDone. Site ready in docs/{iso_id}/")
        else:
            print(f"No data found for {iso_id}. Run the pipeline first.")


if __name__ == "__main__":
    main()
