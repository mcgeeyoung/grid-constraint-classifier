#!/usr/bin/env python3
"""
Grid Constraint → DER Mapping Pipeline

End-to-end orchestrator that:
  1. Pulls PJM zone-level LMP data (or loads from cache)
  2. Computes constraint metrics per zone
  3. Classifies zones as transmission/generation/both/unconstrained
  4. Generates DER deployment recommendations
  5. Creates interactive map and charts
  6. Exports classification_summary.json

Usage:
  python3 run_pipeline.py                    # Full pipeline
  python3 run_pipeline.py --zone-only        # Skip node-level pulls (faster)
  python3 run_pipeline.py --skip-download    # Use cached data only
  python3 run_pipeline.py --year 2024        # Use different year
"""

import argparse
import json
import logging
import sys
import os
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from src.data_acquisition import (
    pull_zone_lmps,
    pull_constrained_zone_pnodes,
    download_transmission_lines,
    download_zone_boundaries,
    get_zone_centroids,
    get_data_center_locations,
    geocode_pnodes,
)
from src.dc_scraper import (
    scrape_state_listings,
    scrape_detail_pages,
    combine_dc_data,
    geocode_dc_addresses,
    build_dc_summary,
    load_dc_data,
)
from src.pjm_gis import (
    fetch_backbone_lines,
    fetch_zone_boundaries as fetch_pjm_zone_boundaries,
    load_pjm_gis_data,
)
from core.constraint_classifier import (
    compute_zone_metrics,
    classify_zones,
    get_constrained_hours,
    get_congestion_value,
)
from core.der_recommender import recommend_ders, format_recommendation_text
from core.pnode_analyzer import analyze_all_constrained_zones, load_pnode_results
from src.visualization import (
    create_interactive_map,
    create_score_bar_chart,
    create_congestion_heatmap,
    create_monthly_trend_chart,
)

OUTPUT_DIR = Path(__file__).parent / "output"


def setup_logging():
    """Configure logging to both file and stdout."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    log_path = OUTPUT_DIR / "pipeline.log"

    handlers = [
        logging.FileHandler(log_path, mode="w"),
        logging.StreamHandler(sys.stdout),
    ]

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        handlers=handlers,
    )
    return logging.getLogger(__name__)


def run_pipeline(
    year: int = 2025,
    skip_download: bool = False,
    zone_only: bool = True,
    pnode_drilldown: bool = False,
    dc_scrape: bool = False,
    pjm_gis: bool = False,
):
    """Execute the full pipeline."""
    logger = setup_logging()
    logger.info("=" * 60)
    logger.info("Grid Constraint → DER Mapping Pipeline")
    logger.info(f"Year: {year} | Skip download: {skip_download} | Zone only: {zone_only} | Pnode drill-down: {pnode_drilldown} | DC scrape: {dc_scrape} | PJM GIS: {pjm_gis}")
    logger.info("=" * 60)

    # Check for API key (required for live pulls, optional with --skip-download)
    has_api_key = bool(os.environ.get("PJM_SUBSCRIPTION_KEY"))
    if not has_api_key and not skip_download:
        logger.error("PJM_SUBSCRIPTION_KEY not set. Export it before running.")
        sys.exit(1)
    if not has_api_key and pnode_drilldown:
        logger.warning("PJM_SUBSCRIPTION_KEY not set. Pnode drill-down will only work if node LMP data is already cached.")

    # ── Phase 1: Data Acquisition ──
    logger.info("Phase 1: Data Acquisition")

    if skip_download:
        cache_path = Path(__file__).parent / "data" / "zone_lmps" / f"zone_lmps_{year}.parquet"
        if not cache_path.exists():
            logger.error(f"No cached data at {cache_path}. Run without --skip-download first.")
            sys.exit(1)

    zone_lmps = pull_zone_lmps(year=year, force=False)
    logger.info(f"Zone LMPs: {len(zone_lmps)} rows, {zone_lmps['pnode_name'].nunique()} zones")

    # Download transmission lines (non-PJM API, no rate limit concern)
    tx_geojson = download_transmission_lines(force=False)
    tx_features = len(tx_geojson.get("features", []))
    logger.info(f"Transmission lines: {tx_features} features")

    # Download zone boundary polygons from HIFLD service territories
    zone_boundary_geojson = download_zone_boundaries(force=False)
    logger.info(f"Zone boundaries: {len(zone_boundary_geojson.get('features', []))} polygons")

    zone_centroids = get_zone_centroids()
    dc_locations_static = get_data_center_locations()

    # ── Phase 1.5a: PJM GIS Data (backbone lines + official zone boundaries) ──
    pjm_backbone_geojson = {"type": "FeatureCollection", "features": []}
    pjm_zones_geojson = {"type": "FeatureCollection", "features": []}

    if pjm_gis:
        logger.info("")
        logger.info("Phase 1.5a: PJM GIS Data (Backbone Lines + Zone Boundaries)")
        pjm_backbone_geojson = fetch_backbone_lines(force=False)
        pjm_zones_geojson = fetch_pjm_zone_boundaries(force=False)
        logger.info(
            f"PJM GIS: {len(pjm_backbone_geojson.get('features', []))} backbone lines, "
            f"{len(pjm_zones_geojson.get('features', []))} zone boundaries"
        )
    else:
        # Try loading cached PJM GIS data
        pjm_backbone_geojson, pjm_zones_geojson = load_pjm_gis_data()

    # Use PJM official zone boundaries if available, otherwise HIFLD
    if pjm_zones_geojson.get("features"):
        zone_boundary_geojson = pjm_zones_geojson
        logger.info("Using PJM official zone boundaries for map")
    else:
        logger.info("Using HIFLD zone boundaries for map (no PJM GIS data)")

    # ── Phase 1.5b: Data Center Overlay ──
    dc_summary = {}
    if dc_scrape:
        logger.info("")
        logger.info("Phase 1.5: Data Center Scrape")
        dc_listings = scrape_state_listings()
        dc_details = scrape_detail_pages(dc_listings)
        dc_records = combine_dc_data(dc_listings, dc_details)
        dc_coordinates = geocode_dc_addresses(dc_records)
        dc_summary = build_dc_summary(dc_records)
        logger.info(f"Data centers: {len(dc_records)} PJM records, {len(dc_coordinates)} geocoded")
    else:
        # Try loading cached data
        dc_records, dc_coordinates = load_dc_data()
        dc_summary = build_dc_summary(dc_records) if dc_records else {}

    # Build map-format DC locations from scraped data or fall back to static
    if dc_records and dc_coordinates:
        dc_locations = []
        for rec in dc_records:
            slug = rec.get("slug", "")
            coord = dc_coordinates.get(slug)
            if not coord:
                continue
            dc_locations.append({
                "name": rec.get("facility_name", ""),
                "lat": coord["lat"],
                "lon": coord["lon"],
                "zone": rec.get("pjm_zone", ""),
                "status": rec.get("status", ""),
                "capacity": rec.get("capacity", ""),
                "capacity_mw": rec.get("capacity_mw", 0),
                "county": rec.get("county", ""),
                "state_code": rec.get("state_code", ""),
                "operator": rec.get("operator", ""),
                "notes": f"{rec.get('operator', '')} | {rec.get('capacity', '')}",
            })
        logger.info(f"Using {len(dc_locations)} scraped DC locations for map")
    else:
        dc_locations = dc_locations_static
        logger.info(f"Using {len(dc_locations)} static DC locations for map")

    # ── Phase 2: Constraint Classification ──
    logger.info("")
    logger.info("Phase 2: Constraint Classification")

    # PJM-specific parameters for core classifier
    pjm_rto_aggregates = {"PJM-RTO", "MID-ATL/APS"}
    pjm_validation_zones = {
        "DOM": "transmission", "PEPCO": "transmission", "BGE": "transmission",
        "PSEG": "transmission", "JCPL": "transmission",
    }

    metrics_df = compute_zone_metrics(zone_lmps, rto_aggregates=pjm_rto_aggregates)
    logger.info(f"Computed metrics for {len(metrics_df)} zones")

    classification_df = classify_zones(metrics_df, validation_zones=pjm_validation_zones)

    # Print classification summary
    logger.info("")
    logger.info("Classification Summary:")
    logger.info("-" * 70)
    for _, row in classification_df.sort_values("transmission_score", ascending=False).iterrows():
        logger.info(
            f"  {row['zone']:10s} | {row['classification']:15s} | "
            f"T={row['transmission_score']:.3f} G={row['generation_score']:.3f} | "
            f"Cong=${row['avg_abs_congestion']:.2f}/MWh"
        )

    # ── Phase 2.5: Pnode Drill-Down (optional, with cached fallback) ──
    pnode_results = {}
    pnode_coordinates = {}
    if pnode_drilldown:
        logger.info("")
        logger.info("Phase 2.5: Pnode Congestion Drill-Down")

        # Build interim summary for zone identification
        interim_scores = []
        for _, row in classification_df.iterrows():
            interim_scores.append({
                "zone": row["zone"],
                "transmission_score": row["transmission_score"],
                "generation_score": row["generation_score"],
            })
        interim_summary = {"zone_scores": interim_scores}

        zone_data = pull_constrained_zone_pnodes(
            interim_summary, year=year, force=False,
        )
        pnode_cache = Path(__file__).parent / "data" / "pnodes" / "pnode_drilldown_results.json"
        pnode_results = analyze_all_constrained_zones(zone_data, cache_path=pnode_cache)
        logger.info(f"Pnode drill-down: {len(pnode_results)} zones analyzed")

        # Geocode pnode names for map display
        logger.info("Geocoding pnode names for map layer...")
        pnode_coordinates = geocode_pnodes(pnode_results)
        logger.info(f"Pnode coordinates: {len(pnode_coordinates)} names resolved")
    else:
        # Load cached pnode results if available
        pnode_cache = Path(__file__).parent / "data" / "pnodes" / "pnode_drilldown_results.json"
        pnode_results = load_pnode_results(pnode_cache)
        if pnode_results:
            pnode_coordinates = geocode_pnodes(pnode_results)
            logger.info(f"Loaded cached pnode data: {len(pnode_results)} zones, {len(pnode_coordinates)} coordinates")

    # ── Phase 3: DER Recommendations ──
    logger.info("")
    logger.info("Phase 3: DER Recommendations")

    recommendations = recommend_ders(classification_df, zone_lmps)

    for rec in recommendations:
        logger.info("")
        logger.info(format_recommendation_text(rec))

    # ── Phase 4: Visualization ──
    logger.info("")
    logger.info("Phase 4: Visualization")

    # Build pnode map data if drill-down was run
    pnode_map_data = None
    if pnode_results and pnode_coordinates:
        pnode_map_data = {"coordinates": pnode_coordinates, "results": pnode_results}

    map_path = create_interactive_map(
        classification_df,
        zone_centroids,
        recommendations,
        dc_locations,
        transmission_geojson=tx_geojson,
        pnode_data=pnode_map_data,
        zone_boundaries=zone_boundary_geojson,
        pjm_backbone_geojson=pjm_backbone_geojson,
    )

    create_score_bar_chart(classification_df)
    create_congestion_heatmap(zone_lmps)
    create_monthly_trend_chart(zone_lmps)

    # ── Phase 5: Export Summary ──
    logger.info("")
    logger.info("Phase 5: Export Summary")

    summary = {
        "metadata": {
            "year": year,
            "total_zone_lmp_rows": len(zone_lmps),
            "zones_analyzed": len(classification_df),
            "transmission_line_features": tx_features,
            "pjm_backbone_lines": len(pjm_backbone_geojson.get("features", [])),
            "pjm_zone_boundaries": len(pjm_zones_geojson.get("features", [])),
        },
        "classifications": {},
        "recommendations": recommendations,
        "zone_scores": [],
    }

    for _, row in classification_df.iterrows():
        summary["classifications"][row["zone"]] = row["classification"]
        summary["zone_scores"].append({
            "zone": row["zone"],
            "classification": row["classification"],
            "transmission_score": round(row["transmission_score"], 4),
            "generation_score": round(row["generation_score"], 4),
            "avg_abs_congestion": round(row["avg_abs_congestion"], 3),
            "avg_lmp": round(row["avg_lmp"], 3),
            "max_congestion": round(row["max_congestion"], 3),
            "congested_hours_pct": round(row["congested_hours_pct"], 4),
        })

    # Classification distribution
    dist = classification_df["classification"].value_counts().to_dict()
    summary["distribution"] = dist

    # Pnode drill-down results
    if pnode_results:
        summary["pnode_drilldown"] = pnode_results

    # Data center summary
    if dc_summary:
        summary["data_centers"] = dc_summary

    summary_path = OUTPUT_DIR / "classification_summary.json"
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)
    logger.info(f"Exported summary to {summary_path}")

    # ── Done ──
    logger.info("")
    logger.info("=" * 60)
    logger.info("Pipeline complete!")
    logger.info(f"  Map:     {map_path}")
    logger.info(f"  Summary: {summary_path}")
    logger.info(f"  Charts:  {OUTPUT_DIR}/")
    logger.info(f"  Log:     {OUTPUT_DIR / 'pipeline.log'}")
    logger.info("=" * 60)

    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Grid Constraint → DER Mapping Pipeline")
    parser.add_argument("--year", type=int, default=2025, help="Year for LMP data (default: 2025)")
    parser.add_argument("--skip-download", action="store_true", help="Use cached data only")
    parser.add_argument("--zone-only", action="store_true", help="Skip node-level data pulls")
    parser.add_argument("--pnode-drilldown", action="store_true", help="Run pnode congestion hotspot analysis for constrained zones")
    parser.add_argument("--dc-scrape", action="store_true", help="Scrape data center listings from interconnection.fyi")
    parser.add_argument("--pjm-gis", action="store_true", help="Fetch backbone lines and zone boundaries from PJM GIS (requires PJM_GIS_USERNAME/PASSWORD)")

    args = parser.parse_args()
    run_pipeline(
        year=args.year,
        skip_download=args.skip_download,
        zone_only=args.zone_only,
        pnode_drilldown=args.pnode_drilldown,
        dc_scrape=args.dc_scrape,
        pjm_gis=args.pjm_gis,
    )
