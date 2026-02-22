"""
Generate GitHub Pages site from grid-constraint-classifier outputs.

Reads:
  output/classification_summary.json

Produces:
  docs/index.html        (executive summary)
  docs/dashboard.html    (copy of full interactive dashboard)
  docs/map.html          (copy of standalone Folium map)

No external dependencies (stdlib only).
"""

import html
import json
import shutil
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "output"
DOCS = ROOT / "docs"

CLASSIFICATION_COLORS = {
    "transmission": "#e74c3c",
    "generation": "#3498db",
    "both": "#9b59b6",
    "unconstrained": "#2ecc71",
}


def load_json() -> dict:
    path = OUTPUT / "classification_summary.json"
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


def build_growth_pressure(data: dict) -> str:
    """Build growth pressure analysis section."""
    cls_map = {zs["zone"]: zs for zs in data["zone_scores"]}
    dc_by_zone = data.get("data_centers", {}).get("by_zone", {})
    constrained_types = {"transmission", "both"}

    pressure_zones = []
    for zone, zdata in dc_by_zone.items():
        zone_scores = cls_map.get(zone, {})
        zone_cls = zone_scores.get("classification", "unconstrained")
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


def build_pnode_summary(data: dict) -> str:
    """Build pnode hotspot summary."""
    pnode_drilldown = data.get("pnode_drilldown", {})
    if not pnode_drilldown:
        return ""

    total_pnodes = 0
    total_critical = 0
    total_elevated = 0
    zones_with_critical = []

    for zone, pd in pnode_drilldown.items():
        total_pnodes += pd.get("total_pnodes", 0)
        critical = pd.get("tier_distribution", {}).get("critical", 0)
        elevated = pd.get("tier_distribution", {}).get("elevated", 0)
        total_critical += critical
        total_elevated += elevated
        if critical > 0:
            zones_with_critical.append(zone)

    return f"""
    <div class="stat-card">
      <div class="stat-value">{total_pnodes}</div>
      <div class="stat-label">Pnodes Analyzed</div>
    </div>
    <div class="stat-card">
      <div class="stat-value">{total_critical}</div>
      <div class="stat-label">Critical Hotspots</div>
    </div>
    """


def build_executive_summary(data: dict) -> str:
    """Generate the full executive summary HTML page."""
    meta = data["metadata"]
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

    # DOM stats
    dom_dc = dc.get("by_zone", {}).get("DOM", {})
    dom_total_dc = dom_dc.get("total", 0)
    dom_proposed_dc = dom_dc.get("proposed", 0)

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

    zone_table_rows = build_zone_table_rows(data)
    growth_pressure = build_growth_pressure(data)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>PJM Grid Constraint Classifier</title>
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
  <h1>PJM Grid Constraint Classifier</h1>
  <div class="subtitle">Identifying where the grid is congested and where DERs can help</div>
  <div class="context">Built by WattCarbon | Data: PJM Interconnection {year}</div>
</div>

<div class="container">

  <!-- What This Tool Does -->
  <div class="section">
    <h2 class="section-title">What This Tool Does</h2>
    <div class="feature-list">
      <ul>
        <li><span class="bullet"></span>
          <span>Pulls <b>{meta['total_zone_lmp_rows']:,}</b> hourly LMP data points from the
          PJM Data Miner 2 API ({year}), decomposing each into congestion, energy, and loss components</span></li>
        <li><span class="bullet"></span>
          <span>Classifies all <b>{meta['zones_analyzed']}</b> PJM pricing zones as
          transmission-constrained, generation-constrained, both, or unconstrained using weighted
          multi-factor scoring</span></li>
        <li><span class="bullet"></span>
          <span>Drills down to <b>{total_pnodes}</b> individual pricing nodes (pnodes) with
          severity scoring and 12x24 constraint loadshapes showing monthly/hourly congestion patterns</span></li>
        <li><span class="bullet"></span>
          <span>Scrapes <b>{dc_total:,}</b> data center records from interconnection queues and
          maps them to PJM zones, identifying growth pressure areas</span></li>
        <li><span class="bullet"></span>
          <span>Overlays PJM GIS backbone transmission lines (<b>{meta['pjm_backbone_lines']}</b>
          lines, 345-765kV) and official zone boundaries on an interactive map</span></li>
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
      <div class="stat-card">
        <div class="stat-value">{dc_total:,}</div>
        <div class="stat-label">PJM Data Centers</div>
        <div class="stat-detail">{dc_mw:,.0f} MW estimated capacity,
        {dc_proposed} proposed</div>
      </div>
      <div class="stat-card highlight">
        <div class="stat-value">{dom_total_dc:,}</div>
        <div class="stat-label">DOM Data Centers</div>
        <div class="stat-detail">{dom_proposed_dc} proposed. #1 growth pressure zone</div>
      </div>
      <div class="stat-card">
        <div class="stat-value">{total_pnodes}</div>
        <div class="stat-label">Pnodes Analyzed</div>
        <div class="stat-detail">{total_critical} critical hotspots across
        {len(pnode_drilldown)} zones</div>
      </div>
      <div class="stat-card">
        <div class="stat-value">{meta['pjm_backbone_lines']}</div>
        <div class="stat-label">Transmission Lines Mapped</div>
        <div class="stat-detail">345-765kV backbone, {meta['pjm_zone_boundaries']} zone boundaries</div>
      </div>
    </div>
  </div>

  <!-- How It Works -->
  <div class="section">
    <h2 class="section-title">How It Works</h2>
    <div class="pipeline">
      <div class="pipeline-step">
        <div class="pipeline-phase">Phase 1</div>
        <div class="pipeline-name">Data Acquisition</div>
        <div class="pipeline-desc">PJM API hourly LMPs + HIFLD transmission + PJM GIS backbone lines and zone boundaries</div>
      </div>
      <div class="pipeline-step">
        <div class="pipeline-phase">Phase 1.5</div>
        <div class="pipeline-name">Data Center Scrape</div>
        <div class="pipeline-desc">Interconnection queue scraping, geocoding, and zone mapping for {dc_total:,} facilities</div>
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
          <b>LMP data:</b> PJM Data Miner 2 API, day-ahead hourly LMPs ({year})<br>
          <b>Transmission:</b> PJM GIS ArcGIS REST services (backbone lines 345-765kV)<br>
          <b>Zone boundaries:</b> PJM official zone boundary GIS data<br>
          <b>Data centers:</b> interconnection.fyi PJM queue listings<br>
          <b>Pnode coordinates:</b> PJM pnode metadata + geocoding
        </p>
      </div>
    </div>
  </div>

</div>

<div class="footer">
  Generated {now} | PJM Grid Constraint Classifier |
  Data: PJM Interconnection day-ahead hourly LMPs ({year})
</div>

</body>
</html>"""


def main():
    print("Loading classification summary...")
    data = load_json()

    print("Generating executive summary...")
    summary_html = build_executive_summary(data)

    # Create docs directory
    DOCS.mkdir(exist_ok=True)

    # Write executive summary
    index_path = DOCS / "index.html"
    with open(index_path, "w") as f:
        f.write(summary_html)
    size_kb = index_path.stat().st_size / 1024
    print(f"  docs/index.html ({size_kb:.0f} KB)")

    # Copy dashboard
    dashboard_src = OUTPUT / "dashboard.html"
    dashboard_dst = DOCS / "dashboard.html"
    if dashboard_src.exists():
        shutil.copy2(dashboard_src, dashboard_dst)
        size_mb = dashboard_dst.stat().st_size / 1024 / 1024
        print(f"  docs/dashboard.html ({size_mb:.1f} MB)")
    else:
        print(f"  WARNING: {dashboard_src} not found, skipping")

    # Copy map
    map_src = OUTPUT / "grid_constraint_map.html"
    map_dst = DOCS / "map.html"
    if map_src.exists():
        shutil.copy2(map_src, map_dst)
        size_mb = map_dst.stat().st_size / 1024 / 1024
        print(f"  docs/map.html ({size_mb:.1f} MB)")
    else:
        print(f"  WARNING: {map_src} not found, skipping")

    print("Done. Site ready in docs/")


if __name__ == "__main__":
    main()
