"""
Generate a self-contained HTML dashboard from grid-constraint-classifier outputs.

Reads:
  output/{iso_id}/classification_summary.json
  output/{iso_id}/grid_constraint_map.html
  output/{iso_id}/score_comparison.png
  output/{iso_id}/congestion_heatmap.png
  output/{iso_id}/monthly_congestion_trends.png

Produces:
  output/{iso_id}/dashboard.html

No external dependencies (stdlib only).
"""

import argparse
import base64
import html
import json
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent

CLASSIFICATION_COLORS = {
    "transmission": "#e74c3c",
    "generation": "#3498db",
    "both": "#9b59b6",
    "unconstrained": "#2ecc71",
}

DER_CATEGORY_COLORS = {
    "dispatchable": "#e67e22",
    "consistent": "#16a085",
    "variable": "#f39c12",
}

TIER_COLORS = {
    "critical": "#c0392b",
    "elevated": "#e67e22",
    "moderate": "#f1c40f",
    "low": "#27ae60",
}

CHART_FILES = [
    "score_comparison.png",
    "congestion_heatmap.png",
    "monthly_congestion_trends.png",
]

CHART_TITLES = {
    "score_comparison.png": "Transmission vs Generation Scores",
    "congestion_heatmap.png": "Congestion Heatmap",
    "monthly_congestion_trends.png": "Monthly Congestion Trends",
}


def load_json(output_dir: Path) -> dict:
    path = output_dir / "classification_summary.json"
    with open(path) as f:
        return json.load(f)


def encode_png(output_dir: Path, filename: str) -> str:
    path = output_dir / filename
    if not path.exists():
        return ""
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("ascii")


def load_map_html(output_dir: Path) -> str:
    path = output_dir / "grid_constraint_map.html"
    if not path.exists():
        return "<p>Map not available for this ISO.</p>"
    with open(path) as f:
        return f.read()


def build_stat_cards(data: dict) -> str:
    meta = data["metadata"]
    dist = data["distribution"]

    badges = []
    for cls in ("transmission", "generation", "both", "unconstrained"):
        count = dist.get(cls, 0)
        color = CLASSIFICATION_COLORS[cls]
        badges.append(
            f'<span class="badge" style="background:{color}">'
            f"{cls.title()}: {count}</span>"
        )
    badge_html = " ".join(badges)

    return f"""
    <div class="stat-cards">
      <div class="stat-card">
        <div class="stat-value">{meta["year"]}</div>
        <div class="stat-label">Analysis Year</div>
      </div>
      <div class="stat-card">
        <div class="stat-value">{meta["total_zone_lmp_rows"]:,}</div>
        <div class="stat-label">LMP Data Points</div>
      </div>
      <div class="stat-card">
        <div class="stat-value">{meta["zones_analyzed"]}</div>
        <div class="stat-label">Zones Analyzed</div>
      </div>
      <div class="stat-card">
        <div class="stat-value">{badge_html}</div>
        <div class="stat-label">Classification Distribution</div>
      </div>
    </div>
    """


def _build_pnode_section(zone: str, pnode_data: dict) -> str:
    """Build the congestion hotspot HTML section for a zone's accordion row."""
    if not pnode_data or pnode_data.get("total_pnodes", 0) == 0:
        return ""

    tier_dist = pnode_data["tier_distribution"]
    hotspots = pnode_data["hotspots"]

    # Tier distribution badges
    tier_badges = []
    for tier in ("critical", "elevated", "moderate", "low"):
        count = tier_dist.get(tier, 0)
        color = TIER_COLORS[tier]
        tier_badges.append(
            f'<span class="tier-badge" style="background:{color}">'
            f'{tier.title()}: {count}</span>'
        )
    badges_html = " ".join(tier_badges)

    # Hotspot mini-table
    hotspot_rows = []
    for hs in hotspots:
        tier = hs["tier"]
        tier_color = TIER_COLORS[tier]
        hotspot_rows.append(
            f"<tr>"
            f"<td>{html.escape(str(hs['pnode_name']))}</td>"
            f"<td>{hs['severity_score']:.4f}</td>"
            f"<td>${hs['avg_congestion']:.2f}</td>"
            f"<td>${hs['max_congestion']:.2f}</td>"
            f"<td>{hs['congested_hours_pct']:.1%}</td>"
            f"<td>{hs['peak_offpeak_ratio']:.2f}</td>"
            f"<td>{hs['extreme_event_hours']}</td>"
            f'<td><span class="tier-badge" style="background:{tier_color}">{tier}</span></td>'
            f"</tr>"
        )
    rows_html = "\n".join(hotspot_rows)

    # Loadshape heatmaps for top 5 hotspots
    loadshape_html = _build_loadshape_heatmaps(hotspots)

    return f"""
    <div class="pnode-section">
      <h4 class="pnode-heading">Congestion Hotspots ({pnode_data['total_pnodes']} pnodes)</h4>
      <div class="tier-summary">{badges_html}</div>
      <div class="pnode-table-wrap">
        <table class="pnode-table" data-zone="{html.escape(zone)}">
          <thead>
            <tr>
              <th data-col="0" data-type="str">Pnode <span class="sort-arrow">&udarr;</span></th>
              <th data-col="1" data-type="num">Severity <span class="sort-arrow">&udarr;</span></th>
              <th data-col="2" data-type="num">Avg $/MWh <span class="sort-arrow">&udarr;</span></th>
              <th data-col="3" data-type="num">Max $/MWh <span class="sort-arrow">&udarr;</span></th>
              <th data-col="4" data-type="num">Constrained % <span class="sort-arrow">&udarr;</span></th>
              <th data-col="5" data-type="num">Pk/OffPk <span class="sort-arrow">&udarr;</span></th>
              <th data-col="6" data-type="num">Extreme Hrs <span class="sort-arrow">&udarr;</span></th>
              <th data-col="7" data-type="str">Tier <span class="sort-arrow">&udarr;</span></th>
            </tr>
          </thead>
          <tbody>
            {rows_html}
          </tbody>
        </table>
      </div>
      {loadshape_html}
    </div>
    """


MONTH_LABELS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                 "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _build_loadshape_heatmaps(hotspots: list) -> str:
    """Render 12x24 CSS heatmap tables for top 5 hotspots with constraint loadshapes."""
    cards = []
    for hs in hotspots[:5]:
        ls = hs.get("constraint_loadshape")
        max_mwh = hs.get("constraint_loadshape_max_mwh", 0)
        if not ls:
            continue

        pnode_name = html.escape(str(hs["pnode_name"]))

        # Build heatmap rows: 12 months x 24 hours
        heatmap_rows = []
        for m in range(1, 13):
            month_key = str(m)
            coeffs = ls.get(month_key, [0.0] * 24)
            cells = []
            for h, coeff in enumerate(coeffs):
                # Color: white (0) to red (1) via rgba
                r, g, b = 220, 50, 47  # base red
                alpha = round(coeff * 0.85 + 0.05, 3) if coeff > 0.01 else 0.0
                bg = f"rgba({r},{g},{b},{alpha})" if alpha > 0 else "#fff"
                approx_dollar = round(coeff * max_mwh, 2)
                tooltip = f"Month {m}, Hour {h}: coeff={coeff:.3f}, ~${approx_dollar}/MWh"
                cells.append(
                    f'<td class="ls-cell" style="background:{bg}" '
                    f'title="{tooltip}">{coeff:.2f}</td>'
                )
            cells_html = "".join(cells)
            heatmap_rows.append(
                f"<tr><td class='ls-month'>{MONTH_LABELS[m-1]}</td>{cells_html}</tr>"
            )
        rows_html = "\n".join(heatmap_rows)

        # Hour header row
        hour_headers = "".join(f"<th>{h}</th>" for h in range(24))

        cards.append(f"""
        <div class="loadshape-card">
          <div class="loadshape-title">{pnode_name}
            <span class="loadshape-max">(peak: ${max_mwh:.2f}/MWh)</span>
          </div>
          <div class="ls-heatmap-wrap">
            <table class="ls-heatmap">
              <thead><tr><th></th>{hour_headers}</tr></thead>
              <tbody>{rows_html}</tbody>
            </table>
          </div>
        </div>
        """)

    if not cards:
        return ""

    return f"""
    <div class="loadshape-section">
      <h4 class="pnode-heading">Constraint Load Shapes (Monthly x Hourly)</h4>
      <p class="loadshape-desc">Hover cells for coefficient and approx. $/MWh. Red intensity = constraint severity relative to pnode peak.</p>
      {"".join(cards)}
    </div>
    """


def _build_zone_heatmap(zone: str, heatmap_data: dict) -> str:
    """Render a 12x24 CSS heatmap table for zone-level congestion."""
    if not heatmap_data:
        return ""

    data_map = heatmap_data["data"]
    max_val = heatmap_data.get("max_congestion", 1.0) or 1.0
    zone_esc = html.escape(zone)

    heatmap_rows = []
    for m in range(1, 13):
        values = data_map.get(str(m), [0.0] * 24)
        cells = []
        for h, val in enumerate(values):
            frac = val / max_val if max_val > 0 else 0
            r, g, b = 220, 50, 47
            alpha = round(frac * 0.85 + 0.05, 3) if frac > 0.01 else 0.0
            bg = f"rgba({r},{g},{b},{alpha})" if alpha > 0 else "#fff"
            tooltip = f"Month {m}, Hour {h}: ${val:.2f}/MWh"
            cells.append(
                f'<td class="ls-cell" style="background:{bg}" '
                f'title="{tooltip}">${val:.2f}</td>'
            )
        cells_html = "".join(cells)
        heatmap_rows.append(
            f"<tr><td class='ls-month'>{MONTH_LABELS[m-1]}</td>{cells_html}</tr>"
        )
    rows_html = "\n".join(heatmap_rows)
    hour_headers = "".join(f"<th>{h}</th>" for h in range(24))

    return f"""
    <div class="loadshape-section">
      <h4 class="pnode-heading">Zone Congestion Heatmap (Monthly x Hourly)</h4>
      <p class="loadshape-desc">Mean |congestion| $/MWh by month and hour. Red intensity scales to zone peak (${max_val:.2f}/MWh).</p>
      <div class="loadshape-card">
        <div class="loadshape-title">{zone_esc}
          <span class="loadshape-max">(peak: ${max_val:.2f}/MWh)</span>
        </div>
        <div class="ls-heatmap-wrap">
          <table class="ls-heatmap">
            <thead><tr><th></th>{hour_headers}</tr></thead>
            <tbody>{rows_html}</tbody>
          </table>
        </div>
      </div>
    </div>
    """


def build_zone_table(data: dict) -> str:
    # Build lookup from recommendations keyed by zone
    rec_map = {r["zone"]: r for r in data["recommendations"]}
    pnode_drilldown = data.get("pnode_drilldown", {})
    zone_heatmaps = data.get("zone_heatmaps", {})

    rows = []
    for zs in data["zone_scores"]:
        zone = zs["zone"]
        cls = zs["classification"]
        color = CLASSIFICATION_COLORS[cls]
        rec = rec_map.get(zone, {})

        # Build DER recommendation detail
        der_parts = []
        for level in ("primary_recommendation", "secondary_recommendation", "tertiary_recommendation"):
            r = rec.get(level)
            if not r:
                continue
            cat = r["category"]
            cat_color = DER_CATEGORY_COLORS.get(cat, "#888")
            asset_labels = ", ".join(a["label"] for a in r["assets"])
            priority_label = level.replace("_recommendation", "").title()
            der_parts.append(
                f'<div class="der-row">'
                f'<span class="der-priority">{priority_label}</span>'
                f'<span class="der-cat" style="background:{cat_color}">{cat}</span>'
                f'<span class="der-assets">{html.escape(asset_labels)}</span>'
                f'<div class="der-reason">{html.escape(r["reason"])}</div>'
                f"</div>"
            )
        der_html = "".join(der_parts) if der_parts else "<em>No recommendations</em>"
        rationale = html.escape(rec.get("rationale", ""))

        annual_hrs = rec.get("annual_constrained_hours", "")
        annual_hrs_display = f"{annual_hrs:,}" if isinstance(annual_hrs, int) else str(annual_hrs)

        # Build pnode hotspot section (only for constrained zones with data)
        pnode_html = _build_pnode_section(zone, pnode_drilldown.get(zone))

        # Build zone-level 12x24 congestion heatmap
        zone_hm_data = zone_heatmaps.get(zone)
        zone_hm_html = _build_zone_heatmap(zone, zone_hm_data) if zone_hm_data else ""

        rows.append(
            f'<tr class="zone-row" data-zone="{html.escape(zone)}">'
            f"<td>{html.escape(zone)}</td>"
            f'<td><span class="cls-badge" style="background:{color}">{cls}</span></td>'
            f"<td>{zs['transmission_score']:.4f}</td>"
            f"<td>{zs['generation_score']:.4f}</td>"
            f"<td>${zs['avg_abs_congestion']:.2f}</td>"
            f"<td>${zs['max_congestion']:.2f}</td>"
            f"<td>{zs['congested_hours_pct']:.1%}</td>"
            f"<td>{annual_hrs_display}</td>"
            f"</tr>"
            f'<tr class="detail-row" data-zone="{html.escape(zone)}">'
            f'<td colspan="8">'
            f'<div class="detail-content">'
            f'<div class="detail-rationale">{rationale}</div>'
            f'<div class="der-grid">{der_html}</div>'
            f'{zone_hm_html}'
            f'{pnode_html}'
            f"</div></td></tr>"
        )

    return "\n".join(rows)


def build_charts(charts: dict[str, str]) -> str:
    parts = []
    score_b64 = charts.get("score_comparison.png", "")
    heatmap_b64 = charts.get("congestion_heatmap.png", "")
    trends_b64 = charts.get("monthly_congestion_trends.png", "")

    row_cards = []
    if score_b64:
        row_cards.append(f"""
      <div class="chart-card">
        <h3>{CHART_TITLES["score_comparison.png"]}</h3>
        <img src="data:image/png;base64,{score_b64}" alt="Score Comparison">
      </div>""")
    if heatmap_b64:
        row_cards.append(f"""
      <div class="chart-card">
        <h3>{CHART_TITLES["congestion_heatmap.png"]}</h3>
        <img src="data:image/png;base64,{heatmap_b64}" alt="Congestion Heatmap">
      </div>""")
    if row_cards:
        parts.append(f'<div class="charts-row">{"".join(row_cards)}</div>')
    if trends_b64:
        parts.append(f"""
    <div class="chart-card chart-full">
      <h3>{CHART_TITLES["monthly_congestion_trends.png"]}</h3>
      <img src="data:image/png;base64,{trends_b64}" alt="Monthly Trends">
    </div>""")

    return "\n".join(parts) if parts else "<p>No charts available.</p>"


def build_methodology() -> str:
    return """
    <div class="methodology-grid">
      <div class="method-card">
        <h3>Transmission Score</h3>
        <p>Weighted composite of congestion-based metrics:</p>
        <table class="method-table">
          <tr><td>Congestion Ratio</td><td>|congestion| / |LMP|</td><td>30%</td></tr>
          <tr><td>Congestion Volatility</td><td>Std dev of congestion prices</td><td>25%</td></tr>
          <tr><td>Congested Hours %</td><td>Hours with |congestion| > $2/MWh</td><td>25%</td></tr>
          <tr><td>Peak/Off-Peak Ratio</td><td>Peak vs off-peak congestion</td><td>20%</td></tr>
        </table>
      </div>
      <div class="method-card">
        <h3>Generation Score</h3>
        <p>Weighted composite of energy-price metrics:</p>
        <table class="method-table">
          <tr><td>Energy Deviation</td><td>Zone vs system energy price</td><td>35%</td></tr>
          <tr><td>Energy Volatility</td><td>Energy price std/mean</td><td>30%</td></tr>
          <tr><td>Loss Component</td><td>Marginal loss ratio</td><td>20%</td></tr>
          <tr><td>High Energy Hours %</td><td>Hours > avg + $3/MWh</td><td>15%</td></tr>
        </table>
      </div>
      <div class="method-card method-full">
        <h3>Classification Rules</h3>
        <div class="rules-grid">
          <div class="rule">
            <span class="cls-badge" style="background:#9b59b6">both</span>
            T-score &ge; 0.5 AND G-score &ge; 0.5
          </div>
          <div class="rule">
            <span class="cls-badge" style="background:#e74c3c">transmission</span>
            T-score &ge; 0.5 AND G-score &lt; 0.5
          </div>
          <div class="rule">
            <span class="cls-badge" style="background:#3498db">generation</span>
            T-score &lt; 0.5 AND G-score &ge; 0.5
          </div>
          <div class="rule">
            <span class="cls-badge" style="background:#2ecc71">unconstrained</span>
            T-score &lt; 0.5 AND G-score &lt; 0.5
          </div>
        </div>
      </div>
    </div>
    """


def build_dc_section(data: dict, iso_name: str = "PJM") -> str:
    """Build Data Centers dashboard section with stats, growth pressure, and zone table."""
    dc = data.get("data_centers", {})
    if not dc:
        return ""

    total = dc.get("total_count", 0)
    total_mw = dc.get("total_estimated_mw", 0)
    status_totals = dc.get("status_totals", {})
    by_zone = dc.get("by_zone", {})

    operational = status_totals.get("operational", 0)
    proposed = status_totals.get("proposed", 0)
    construction = status_totals.get("construction", 0)

    # Build classification lookup for constraint info
    cls_map = {}
    for zs in data.get("zone_scores", []):
        cls_map[zs["zone"]] = zs["classification"]

    # Stat cards
    stat_cards = f"""
    <div class="stat-cards">
      <div class="stat-card">
        <div class="stat-value">{total:,}</div>
        <div class="stat-label">{iso_name} Data Centers</div>
      </div>
      <div class="stat-card">
        <div class="stat-value">{total_mw:,.0f} MW</div>
        <div class="stat-label">Estimated Total Capacity</div>
      </div>
      <div class="stat-card">
        <div class="stat-value">{operational:,}</div>
        <div class="stat-label">Operational</div>
      </div>
      <div class="stat-card">
        <div class="stat-value">{proposed:,}</div>
        <div class="stat-label">Proposed</div>
      </div>
    </div>
    """

    # Growth Pressure: zones that are constrained AND have 5+ proposed DCs
    constrained_types = {"transmission", "both"}
    pressure_zones = []
    for zone, zdata in by_zone.items():
        zone_cls = cls_map.get(zone, "unconstrained")
        if zone_cls in constrained_types and zdata.get("proposed", 0) >= 5:
            pressure_zones.append({
                "zone": zone,
                "classification": zone_cls,
                "proposed": zdata["proposed"],
                "total": zdata["total"],
                "estimated_mw": zdata["estimated_mw"],
            })

    pressure_html = ""
    if pressure_zones:
        pressure_items = []
        for pz in sorted(pressure_zones, key=lambda x: -x["proposed"]):
            cls_color = CLASSIFICATION_COLORS.get(pz["classification"], "#888")
            pressure_items.append(
                f'<li><b>{html.escape(pz["zone"])}</b> '
                f'<span class="cls-badge" style="background:{cls_color}">{pz["classification"]}</span> '
                f'&mdash; {pz["proposed"]} proposed, {pz["total"]} total, '
                f'~{pz["estimated_mw"]:,.0f} MW</li>'
            )
        pressure_html = f"""
        <div class="pressure-callout">
          <h3>Growth Pressure Zones</h3>
          <p>These grid-constrained zones have significant proposed data center growth:</p>
          <ul>{"".join(pressure_items)}</ul>
        </div>
        """

    # Zone DC table
    table_rows = []
    for zone in sorted(by_zone.keys()):
        zdata = by_zone[zone]
        zone_cls = cls_map.get(zone, "unconstrained")
        cls_color = CLASSIFICATION_COLORS.get(zone_cls, "#888")
        is_pressure = (
            zone_cls in constrained_types and zdata.get("proposed", 0) >= 5
        )
        row_class = ' class="dc-pressure-row"' if is_pressure else ""

        top_county = zdata["top_counties"][0]["name"] if zdata.get("top_counties") else ""

        table_rows.append(
            f"<tr{row_class}>"
            f"<td>{html.escape(zone)}</td>"
            f'<td><span class="cls-badge" style="background:{cls_color}">{zone_cls}</span></td>'
            f"<td>{zdata['total']}</td>"
            f"<td>{zdata.get('operational', 0)}</td>"
            f"<td>{zdata.get('proposed', 0)}</td>"
            f"<td>{zdata.get('construction', 0)}</td>"
            f"<td>{zdata['estimated_mw']:,.0f}</td>"
            f"<td>{html.escape(top_county)}</td>"
            f"</tr>"
        )

    rows_html = "\n".join(table_rows)

    table_html = f"""
    <div class="table-wrap">
      <table class="zone-table" id="dcZoneTable">
        <thead>
          <tr>
            <th data-col="0" data-type="str">Zone <span class="sort-arrow">&udarr;</span></th>
            <th data-col="1" data-type="str">Classification <span class="sort-arrow">&udarr;</span></th>
            <th data-col="2" data-type="num">Total DCs <span class="sort-arrow">&udarr;</span></th>
            <th data-col="3" data-type="num">Operational <span class="sort-arrow">&udarr;</span></th>
            <th data-col="4" data-type="num">Proposed <span class="sort-arrow">&udarr;</span></th>
            <th data-col="5" data-type="num">Construction <span class="sort-arrow">&udarr;</span></th>
            <th data-col="6" data-type="num">Est. MW <span class="sort-arrow">&udarr;</span></th>
            <th data-col="7" data-type="str">Top County <span class="sort-arrow">&udarr;</span></th>
          </tr>
        </thead>
        <tbody>
          {rows_html}
        </tbody>
      </table>
    </div>
    """

    return f"""
    {stat_cards}
    {pressure_html}
    {table_html}
    """


def build_html(data: dict, charts: dict[str, str], map_html: str, iso_name: str = "PJM") -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    year = data["metadata"]["year"]
    stat_cards = build_stat_cards(data)
    zone_rows = build_zone_table(data)
    chart_section = build_charts(charts)
    methodology = build_methodology()
    dc_section = build_dc_section(data, iso_name=iso_name)
    escaped_map = html.escape(map_html)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{iso_name} Grid Constraint Dashboard ({year})</title>
<style>
/* ── Reset & base ── */
*, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  background: #f5f6fa;
  color: #2c3e50;
  line-height: 1.5;
}}

/* ── Header ── */
.header {{
  background: linear-gradient(135deg, #2c3e50, #34495e);
  color: #fff;
  padding: 2rem 2rem 1.5rem;
}}
.header h1 {{ font-size: 1.75rem; font-weight: 700; margin-bottom: 0.25rem; }}
.header .subtitle {{ color: #bdc3c7; font-size: 0.95rem; }}

/* ── Stat cards ── */
.stat-cards {{
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 1rem;
  padding: 1.5rem 2rem;
  margin-top: -1rem;
}}
.stat-card {{
  background: #fff;
  border-radius: 8px;
  padding: 1.25rem;
  box-shadow: 0 2px 8px rgba(0,0,0,0.08);
  text-align: center;
}}
.stat-value {{ font-size: 1.5rem; font-weight: 700; color: #2c3e50; }}
.stat-label {{ font-size: 0.8rem; color: #7f8c8d; margin-top: 0.25rem; text-transform: uppercase; letter-spacing: 0.5px; }}
.badge {{
  display: inline-block;
  padding: 0.2em 0.6em;
  border-radius: 4px;
  color: #fff;
  font-size: 0.75rem;
  font-weight: 600;
}}

/* ── Nav ── */
.section-nav {{
  position: sticky;
  top: 0;
  z-index: 100;
  background: #fff;
  border-bottom: 1px solid #e0e0e0;
  padding: 0 2rem;
  display: flex;
  gap: 0;
  box-shadow: 0 2px 4px rgba(0,0,0,0.04);
}}
.section-nav a {{
  display: block;
  padding: 0.75rem 1.25rem;
  text-decoration: none;
  color: #7f8c8d;
  font-size: 0.85rem;
  font-weight: 600;
  border-bottom: 3px solid transparent;
  transition: color 0.2s, border-color 0.2s;
}}
.section-nav a:hover {{
  color: #2c3e50;
  border-bottom-color: #3498db;
}}

/* ── Sections ── */
.section {{
  padding: 2rem;
  max-width: 1400px;
  margin: 0 auto;
}}
.section-title {{
  font-size: 1.3rem;
  font-weight: 700;
  margin-bottom: 1rem;
  padding-bottom: 0.5rem;
  border-bottom: 2px solid #e0e0e0;
}}

/* ── Map ── */
.map-container {{
  border-radius: 8px;
  overflow: hidden;
  box-shadow: 0 2px 12px rgba(0,0,0,0.1);
  background: #fff;
}}
.map-container iframe {{
  width: 100%;
  height: 600px;
  border: none;
}}

/* ── Table ── */
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
  padding: 0.75rem 0.75rem;
  text-align: left;
  font-weight: 600;
  cursor: pointer;
  user-select: none;
  white-space: nowrap;
  position: relative;
}}
table.zone-table th:hover {{ background: #2c3e50; }}
table.zone-table th .sort-arrow {{ margin-left: 4px; font-size: 0.7rem; opacity: 0.5; }}
table.zone-table th .sort-arrow.active {{ opacity: 1; }}
table.zone-table td {{ padding: 0.65rem 0.75rem; border-bottom: 1px solid #ecf0f1; }}
.zone-row {{ cursor: pointer; transition: background 0.15s; }}
.zone-row:hover {{ background: #f8f9fa; }}
.cls-badge {{
  display: inline-block;
  padding: 0.15em 0.55em;
  border-radius: 4px;
  color: #fff;
  font-size: 0.78rem;
  font-weight: 600;
  white-space: nowrap;
}}

/* ── Detail rows ── */
.detail-row {{ display: none; }}
.detail-row.open {{ display: table-row; }}
.detail-row td {{ background: #f8f9fa; padding: 0; }}
.detail-content {{
  padding: 1rem 1.5rem;
  animation: slideDown 0.2s ease-out;
}}
@keyframes slideDown {{
  from {{ opacity: 0; transform: translateY(-8px); }}
  to {{ opacity: 1; transform: translateY(0); }}
}}
.detail-rationale {{
  font-size: 0.85rem;
  color: #555;
  margin-bottom: 0.75rem;
  line-height: 1.6;
}}
.der-grid {{ display: flex; flex-wrap: wrap; gap: 0.75rem; }}
.der-row {{
  background: #fff;
  border: 1px solid #e0e0e0;
  border-radius: 6px;
  padding: 0.75rem 1rem;
  flex: 1 1 220px;
  min-width: 220px;
}}
.der-priority {{
  font-weight: 700;
  font-size: 0.75rem;
  text-transform: uppercase;
  color: #7f8c8d;
  margin-right: 0.5rem;
}}
.der-cat {{
  display: inline-block;
  padding: 0.1em 0.5em;
  border-radius: 3px;
  color: #fff;
  font-size: 0.72rem;
  font-weight: 600;
  text-transform: capitalize;
}}
.der-assets {{
  display: block;
  margin-top: 0.35rem;
  font-weight: 600;
  font-size: 0.85rem;
}}
.der-reason {{
  font-size: 0.78rem;
  color: #666;
  margin-top: 0.25rem;
}}

/* ── Pnode hotspot section ── */
.pnode-section {{
  margin-top: 1rem;
  padding-top: 1rem;
  border-top: 1px solid #e0e0e0;
}}
.pnode-heading {{
  font-size: 0.9rem;
  font-weight: 700;
  color: #34495e;
  margin-bottom: 0.5rem;
}}
.tier-summary {{
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
.pnode-table-wrap {{
  overflow-x: auto;
}}
table.pnode-table {{
  width: 100%;
  border-collapse: collapse;
  font-size: 0.8rem;
}}
table.pnode-table th {{
  background: #5d6d7e;
  color: #fff;
  padding: 0.5rem 0.6rem;
  text-align: left;
  font-weight: 600;
  cursor: pointer;
  user-select: none;
  white-space: nowrap;
  font-size: 0.75rem;
}}
table.pnode-table th:hover {{ background: #4a5a6a; }}
table.pnode-table th .sort-arrow {{ margin-left: 3px; font-size: 0.65rem; opacity: 0.5; }}
table.pnode-table th .sort-arrow.active {{ opacity: 1; }}
table.pnode-table td {{
  padding: 0.4rem 0.6rem;
  border-bottom: 1px solid #ecf0f1;
  white-space: nowrap;
}}
table.pnode-table tbody tr:hover {{ background: #eef2f7; }}

/* ── Loadshape heatmaps ── */
.loadshape-section {{
  margin-top: 1rem;
  padding-top: 0.75rem;
  border-top: 1px dashed #ccc;
}}
.loadshape-desc {{
  font-size: 0.78rem;
  color: #7f8c8d;
  margin-bottom: 0.75rem;
}}
.loadshape-card {{
  background: #fff;
  border: 1px solid #e0e0e0;
  border-radius: 6px;
  padding: 0.75rem;
  margin-bottom: 0.75rem;
}}
.loadshape-title {{
  font-size: 0.82rem;
  font-weight: 700;
  color: #34495e;
  margin-bottom: 0.5rem;
}}
.loadshape-max {{
  font-weight: 400;
  color: #7f8c8d;
  font-size: 0.75rem;
}}
.ls-heatmap-wrap {{
  overflow-x: auto;
}}
table.ls-heatmap {{
  border-collapse: collapse;
  font-size: 0.65rem;
  white-space: nowrap;
}}
table.ls-heatmap th {{
  background: #5d6d7e;
  color: #fff;
  padding: 0.25rem 0.35rem;
  text-align: center;
  font-weight: 600;
  font-size: 0.6rem;
}}
table.ls-heatmap td.ls-month {{
  background: #5d6d7e;
  color: #fff;
  padding: 0.25rem 0.4rem;
  font-weight: 600;
  font-size: 0.65rem;
  text-align: right;
}}
table.ls-heatmap td.ls-cell {{
  padding: 0.2rem 0.3rem;
  text-align: center;
  border: 1px solid #f0f0f0;
  font-size: 0.6rem;
  color: #444;
  min-width: 2rem;
  cursor: default;
}}
table.ls-heatmap td.ls-cell:hover {{
  outline: 2px solid #2c3e50;
  z-index: 1;
  position: relative;
}}

/* ── Charts ── */
.charts-row {{
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1.5rem;
  margin-bottom: 1.5rem;
}}
.chart-card {{
  background: #fff;
  border-radius: 8px;
  padding: 1.25rem;
  box-shadow: 0 2px 8px rgba(0,0,0,0.08);
}}
.chart-card h3 {{ font-size: 0.95rem; margin-bottom: 0.75rem; color: #34495e; }}
.chart-card img {{ width: 100%; height: auto; border-radius: 4px; }}
.chart-full {{ width: 100%; }}

/* ── Methodology ── */
.methodology-grid {{
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1.5rem;
}}
.method-card {{
  background: #fff;
  border-radius: 8px;
  padding: 1.25rem;
  box-shadow: 0 2px 8px rgba(0,0,0,0.08);
}}
.method-card h3 {{ font-size: 0.95rem; margin-bottom: 0.5rem; color: #34495e; }}
.method-card p {{ font-size: 0.82rem; color: #666; margin-bottom: 0.5rem; }}
.method-full {{ grid-column: 1 / -1; }}
.method-table {{ width: 100%; font-size: 0.82rem; border-collapse: collapse; }}
.method-table td {{ padding: 0.4rem 0.5rem; border-bottom: 1px solid #ecf0f1; }}
.method-table td:last-child {{ text-align: right; font-weight: 600; color: #2c3e50; }}
.rules-grid {{ display: flex; flex-wrap: wrap; gap: 1rem; margin-top: 0.5rem; }}
.rule {{
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.85rem;
  background: #f8f9fa;
  padding: 0.5rem 1rem;
  border-radius: 6px;
}}

/* ── Data Center Pressure ── */
.pressure-callout {{
  background: #fef9e7;
  border: 2px solid #f1c40f;
  border-radius: 8px;
  padding: 1.25rem 1.5rem;
  margin-bottom: 1.5rem;
}}
.pressure-callout h3 {{
  font-size: 1rem;
  color: #7d6608;
  margin-bottom: 0.5rem;
}}
.pressure-callout p {{
  font-size: 0.85rem;
  color: #7d6608;
  margin-bottom: 0.5rem;
}}
.pressure-callout ul {{
  list-style: none;
  padding: 0;
}}
.pressure-callout li {{
  font-size: 0.85rem;
  color: #2c3e50;
  padding: 0.3rem 0;
}}
tr.dc-pressure-row {{
  background: #fef9e7;
}}
tr.dc-pressure-row:hover {{
  background: #fcf3cf;
}}

/* ── Footer ── */
.footer {{
  text-align: center;
  padding: 2rem;
  color: #95a5a6;
  font-size: 0.78rem;
  border-top: 1px solid #e0e0e0;
  margin-top: 2rem;
}}

/* ── Responsive ── */
@media (max-width: 1024px) {{
  .charts-row {{ grid-template-columns: 1fr; }}
  .methodology-grid {{ grid-template-columns: 1fr; }}
  .method-full {{ grid-column: 1; }}
}}
@media (max-width: 768px) {{
  .stat-cards {{ grid-template-columns: 1fr 1fr; }}
  .section {{ padding: 1rem; }}
  .header {{ padding: 1.25rem; }}
  .header h1 {{ font-size: 1.3rem; }}
  .section-nav {{ overflow-x: auto; }}
  .map-container iframe {{ height: 400px; }}
  .der-grid {{ flex-direction: column; }}
}}
</style>
</head>
<body>

<!-- Header -->
<div class="header">
  <h1>{iso_name} Grid Constraint Dashboard</h1>
  <div class="subtitle">Zone-level constraint analysis with DER investment recommendations</div>
</div>

{stat_cards}

<!-- Navigation -->
<nav class="section-nav">
  <a href="#map">Map</a>
  <a href="#zones">Zone Data</a>
  <a href="#datacenters">Data Centers</a>
  <a href="#charts">Charts</a>
  <a href="#methodology">Methodology</a>
</nav>

<!-- Map Section -->
<div class="section" id="map">
  <h2 class="section-title">Interactive Constraint Map</h2>
  <div class="map-container">
    <iframe srcdoc="{escaped_map}" sandbox="allow-scripts allow-same-origin" loading="lazy"></iframe>
  </div>
</div>

<!-- Zone Data Section -->
<div class="section" id="zones">
  <h2 class="section-title">Zone Classifications &amp; Scores</h2>
  <p style="font-size:0.82rem;color:#7f8c8d;margin-bottom:0.75rem;">Click a row to expand DER recommendations. Click column headers to sort.</p>
  <div class="table-wrap">
    <table class="zone-table" id="zoneTable">
      <thead>
        <tr>
          <th data-col="0" data-type="str">Zone <span class="sort-arrow">&udarr;</span></th>
          <th data-col="1" data-type="str">Classification <span class="sort-arrow">&udarr;</span></th>
          <th data-col="2" data-type="num">T-Score <span class="sort-arrow">&udarr;</span></th>
          <th data-col="3" data-type="num">G-Score <span class="sort-arrow">&udarr;</span></th>
          <th data-col="4" data-type="num">Congestion $/MWh <span class="sort-arrow">&udarr;</span></th>
          <th data-col="5" data-type="num">Max Congestion <span class="sort-arrow">&udarr;</span></th>
          <th data-col="6" data-type="num">Constrained Hrs % <span class="sort-arrow">&udarr;</span></th>
          <th data-col="7" data-type="num">Annual Hrs <span class="sort-arrow">&udarr;</span></th>
        </tr>
      </thead>
      <tbody>
        {zone_rows}
      </tbody>
    </table>
  </div>
</div>

<!-- Data Centers Section -->
<div class="section" id="datacenters">
  <h2 class="section-title">Data Center Overlay</h2>
  {dc_section}
</div>

<!-- Charts Section -->
<div class="section" id="charts">
  <h2 class="section-title">Visualizations</h2>
  {chart_section}
</div>

<!-- Methodology Section -->
<div class="section" id="methodology">
  <h2 class="section-title">Scoring Methodology</h2>
  {methodology}
</div>

<!-- Footer -->
<div class="footer">
  Generated {now} | Data source: {iso_name} day-ahead hourly LMPs ({year})
</div>

<script>
// ── Smooth scroll for nav links ──
document.querySelectorAll('.section-nav a').forEach(function(link) {{
  link.addEventListener('click', function(e) {{
    e.preventDefault();
    var target = document.querySelector(this.getAttribute('href'));
    if (target) {{
      target.scrollIntoView({{ behavior: 'smooth', block: 'start' }});
    }}
  }});
}});

// ── Accordion: click row to expand/collapse ──
document.querySelectorAll('.zone-row').forEach(function(row) {{
  row.addEventListener('click', function() {{
    var zone = this.getAttribute('data-zone');
    var details = document.querySelectorAll('.detail-row');
    details.forEach(function(d) {{
      if (d.getAttribute('data-zone') === zone) {{
        d.classList.toggle('open');
      }} else {{
        d.classList.remove('open');
      }}
    }});
  }});
}});

// ── Sortable table (handles paired data+detail rows) ──
(function() {{
  var table = document.getElementById('zoneTable');
  var thead = table.querySelector('thead');
  var tbody = table.querySelector('tbody');
  var headers = thead.querySelectorAll('th');
  var currentSort = {{ col: -1, asc: true }};

  function getRowPairs() {{
    var rows = tbody.querySelectorAll('tr');
    var pairs = [];
    for (var i = 0; i < rows.length; i += 2) {{
      pairs.push({{ data: rows[i], detail: rows[i + 1] }});
    }}
    return pairs;
  }}

  function parseVal(td, type) {{
    var txt = td.textContent.trim().replace(/[$,%,]/g, '');
    if (type === 'num') {{
      var n = parseFloat(txt);
      return isNaN(n) ? 0 : n;
    }}
    return txt.toLowerCase();
  }}

  headers.forEach(function(th) {{
    th.addEventListener('click', function() {{
      var col = parseInt(this.getAttribute('data-col'));
      var type = this.getAttribute('data-type');
      var asc = (currentSort.col === col) ? !currentSort.asc : true;
      currentSort = {{ col: col, asc: asc }};

      // Update arrows
      headers.forEach(function(h) {{
        var arrow = h.querySelector('.sort-arrow');
        arrow.classList.remove('active');
        arrow.textContent = '\u21C5';
      }});
      var activeArrow = this.querySelector('.sort-arrow');
      activeArrow.classList.add('active');
      activeArrow.textContent = asc ? '\u2191' : '\u2193';

      var pairs = getRowPairs();
      pairs.sort(function(a, b) {{
        var va = parseVal(a.data.children[col], type);
        var vb = parseVal(b.data.children[col], type);
        if (va < vb) return asc ? -1 : 1;
        if (va > vb) return asc ? 1 : -1;
        return 0;
      }});

      // Re-append in sorted order
      pairs.forEach(function(pair) {{
        tbody.appendChild(pair.data);
        tbody.appendChild(pair.detail);
      }});
    }});
  }});
}})();

// ── Sortable pnode mini-tables ──
document.querySelectorAll('table.pnode-table').forEach(function(table) {{
  var thead = table.querySelector('thead');
  var tbody = table.querySelector('tbody');
  var headers = thead.querySelectorAll('th');
  var sortState = {{ col: -1, asc: true }};

  function parseVal(td, type) {{
    var txt = td.textContent.trim().replace(/[$,%,]/g, '');
    if (type === 'num') {{
      var n = parseFloat(txt);
      return isNaN(n) ? 0 : n;
    }}
    return txt.toLowerCase();
  }}

  headers.forEach(function(th) {{
    th.addEventListener('click', function(e) {{
      e.stopPropagation();
      var col = parseInt(this.getAttribute('data-col'));
      var type = this.getAttribute('data-type');
      var asc = (sortState.col === col) ? !sortState.asc : true;
      sortState = {{ col: col, asc: asc }};

      headers.forEach(function(h) {{
        var arrow = h.querySelector('.sort-arrow');
        arrow.classList.remove('active');
        arrow.textContent = '\u21C5';
      }});
      var activeArrow = this.querySelector('.sort-arrow');
      activeArrow.classList.add('active');
      activeArrow.textContent = asc ? '\u2191' : '\u2193';

      var rows = Array.from(tbody.querySelectorAll('tr'));
      rows.sort(function(a, b) {{
        var va = parseVal(a.children[col], type);
        var vb = parseVal(b.children[col], type);
        if (va < vb) return asc ? -1 : 1;
        if (va > vb) return asc ? 1 : -1;
        return 0;
      }});
      rows.forEach(function(row) {{ tbody.appendChild(row); }});
    }});
  }});
}});

// ── Sortable DC zone table ──
(function() {{
  var table = document.getElementById('dcZoneTable');
  if (!table) return;
  var thead = table.querySelector('thead');
  var tbody = table.querySelector('tbody');
  var headers = thead.querySelectorAll('th');
  var sortState = {{ col: -1, asc: true }};

  function parseVal(td, type) {{
    var txt = td.textContent.trim().replace(/[$,%,]/g, '');
    if (type === 'num') {{
      var n = parseFloat(txt);
      return isNaN(n) ? 0 : n;
    }}
    return txt.toLowerCase();
  }}

  headers.forEach(function(th) {{
    th.addEventListener('click', function() {{
      var col = parseInt(this.getAttribute('data-col'));
      var type = this.getAttribute('data-type');
      var asc = (sortState.col === col) ? !sortState.asc : true;
      sortState = {{ col: col, asc: asc }};

      headers.forEach(function(h) {{
        var arrow = h.querySelector('.sort-arrow');
        arrow.classList.remove('active');
        arrow.textContent = '\u21C5';
      }});
      var activeArrow = this.querySelector('.sort-arrow');
      activeArrow.classList.add('active');
      activeArrow.textContent = asc ? '\u2191' : '\u2193';

      var rows = Array.from(tbody.querySelectorAll('tr'));
      rows.sort(function(a, b) {{
        var va = parseVal(a.children[col], type);
        var vb = parseVal(b.children[col], type);
        if (va < vb) return asc ? -1 : 1;
        if (va > vb) return asc ? 1 : -1;
        return 0;
      }});
      rows.forEach(function(row) {{ tbody.appendChild(row); }});
    }});
  }});
}})();
</script>
</body>
</html>"""


def main():
    parser = argparse.ArgumentParser(description="Generate HTML dashboard for an ISO")
    parser.add_argument(
        "--iso", type=str, default="pjm",
        help="ISO identifier (default: pjm). Reads from output/{iso}/",
    )
    args = parser.parse_args()

    iso_id = args.iso.lower()
    output_dir = ROOT / "output" / iso_id

    if not (output_dir / "classification_summary.json").exists():
        print(f"No classification_summary.json found in {output_dir}")
        print(f"Run the pipeline first: python -m cli.run_pipeline --iso {iso_id}")
        return

    print(f"Loading classification summary for {iso_id.upper()}...")
    data = load_json(output_dir)

    iso_name = data.get("metadata", {}).get("iso_name", iso_id.upper())

    print("Encoding charts...")
    charts = {}
    for fname in CHART_FILES:
        charts[fname] = encode_png(output_dir, fname)
        if charts[fname]:
            size_kb = len(charts[fname]) * 3 / 4 / 1024
            print(f"  {fname}: ~{size_kb:.0f} KB")
        else:
            print(f"  {fname}: not found, skipping")

    print("Loading interactive map...")
    map_html = load_map_html(output_dir)

    print(f"Generating {iso_name} dashboard HTML...")
    dashboard = build_html(data, charts, map_html, iso_name=iso_name)

    out_path = output_dir / "dashboard.html"
    with open(out_path, "w") as f:
        f.write(dashboard)

    size_kb = out_path.stat().st_size / 1024
    print(f"Dashboard written to {out_path} ({size_kb:.0f} KB)")


if __name__ == "__main__":
    main()
