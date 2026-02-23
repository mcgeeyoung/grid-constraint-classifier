#!/usr/bin/env python3
"""
Multi-ISO Grid Constraint -> DER Mapping Pipeline

End-to-end orchestrator that works across all 7 US ISOs:
  1. Pulls zone-level LMP data via adapter (gridstatus or custom client)
  2. Computes constraint metrics per zone
  3. Classifies zones as transmission/generation/both/unconstrained
  4. Optionally drills down to pnode congestion hotspots
  5. Generates DER deployment recommendations
  6. Creates interactive map and charts
  7. Exports classification_summary.json

Usage:
  python -m cli.run_pipeline --iso pjm                   # Single ISO
  python -m cli.run_pipeline --iso caiso --year 2024      # CAISO for 2024
  python -m cli.run_pipeline --iso all                    # All 7 ISOs
  python -m cli.run_pipeline --iso pjm --pnode-drilldown  # With pnode analysis
  python -m cli.run_pipeline --iso pjm --dc-scrape        # With DC scraping
"""

import argparse
import json
import logging
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from adapters.registry import get_adapter, SUPPORTED_ISOS
from adapters.base import ISOConfig
from core.constraint_classifier import (
    compute_zone_metrics,
    classify_zones,
)
from core.der_recommender import recommend_ders, format_recommendation_text
from core.pnode_analyzer import analyze_all_constrained_zones, load_pnode_results
from visualization import (
    create_interactive_map,
    create_score_bar_chart,
    create_congestion_heatmap,
    create_monthly_trend_chart,
)

logger = logging.getLogger(__name__)


def setup_logging(output_dir: Path):
    """Configure logging to both file and stdout."""
    output_dir.mkdir(parents=True, exist_ok=True)
    log_path = output_dir / "pipeline.log"

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


def run_single_iso(
    iso_id: str,
    year: int = 2025,
    skip_download: bool = False,
    pnode_drilldown: bool = False,
    dc_scrape: bool = False,
) -> dict:
    """
    Run the full pipeline for a single ISO.

    Returns the classification summary dict.
    """
    data_dir = PROJECT_ROOT / "data"
    output_dir = PROJECT_ROOT / "output" / iso_id

    log = setup_logging(output_dir)
    log.info("=" * 60)
    log.info(f"Grid Constraint -> DER Mapping Pipeline: {iso_id.upper()}")
    log.info(f"Year: {year} | Pnode drill-down: {pnode_drilldown} | DC scrape: {dc_scrape}")
    log.info("=" * 60)

    # Initialize adapter
    adapter = get_adapter(iso_id, data_dir=data_dir)
    config = adapter.config

    # Optional DB writer (fails gracefully if no DB)
    db_writer = None
    try:
        from app.pipeline_writer import get_pipeline_writer
        db_writer = get_pipeline_writer(iso_id, adapter)
        if db_writer:
            db_writer.start_run(year)
            log.info("Database connection active, will persist results")
    except Exception:
        pass

    # -- Phase 1: Data Acquisition --
    log.info("Phase 1: Data Acquisition")

    zone_lmps = adapter.pull_zone_lmps(year=year, force=False)
    if zone_lmps.empty:
        if skip_download:
            log.error(f"No cached data for {iso_id}. Run without --skip-download first.")
            return {}
        log.error(f"Failed to pull zone LMP data for {iso_id}")
        return {}

    log.info(f"Zone LMPs: {len(zone_lmps)} rows, {zone_lmps['pnode_name'].nunique()} zones")

    # Determine zone key for GeoJSON features (used throughout pipeline)
    zone_key = "pjm_zone" if iso_id == "pjm" else "iso_zone"

    # Download transmission lines (HIFLD, works nationwide)
    tx_geojson = {"type": "FeatureCollection", "features": []}
    zone_boundary_geojson = {"type": "FeatureCollection", "features": []}

    try:
        from scraping.hifld import download_transmission_lines, download_zone_boundaries

        tx_cache = data_dir / iso_id / "hifld_transmission_lines.json"
        tx_geojson = download_transmission_lines(cache_path=tx_cache, force=False)
        log.info(f"Transmission lines: {len(tx_geojson.get('features', []))} features")

        if config.hifld_territory_oids:
            boundary_cache = data_dir / iso_id / "zone_boundaries.json"
            zone_boundary_geojson = download_zone_boundaries(
                cache_path=boundary_cache,
                territory_oids=config.hifld_territory_oids,
                zone_property=zone_key,
                force=False,
            )
            log.info(f"Zone boundaries: {len(zone_boundary_geojson.get('features', []))} polygons")
    except Exception as e:
        log.warning(f"HIFLD data unavailable: {e}")

    # NYISO-specific zone boundaries (from NYSERDA ArcGIS)
    if iso_id == "nyiso":
        try:
            from scraping.iso_boundaries import download_nyiso_zone_boundaries
            nyiso_boundaries = download_nyiso_zone_boundaries(
                cache_path=data_dir / iso_id / "zone_boundaries.json",
                force=False,
            )
            if nyiso_boundaries.get("features"):
                zone_boundary_geojson = nyiso_boundaries
                log.info("Using NYISO zone boundaries from NYSERDA")
        except Exception as e:
            log.warning(f"NYISO boundary download failed: {e}")

    # PJM-specific GIS data (backbone lines, official boundaries)
    backbone_geojson = {"type": "FeatureCollection", "features": []}
    if iso_id == "pjm":
        try:
            from src.pjm_gis import load_pjm_gis_data
            pjm_backbone, pjm_zones = load_pjm_gis_data()
            backbone_geojson = pjm_backbone
            if pjm_zones.get("features"):
                zone_boundary_geojson = pjm_zones
                log.info("Using PJM official zone boundaries")
        except Exception as e:
            log.debug(f"PJM GIS data unavailable: {e}")

    zone_centroids = config.get_zone_centroids()

    # -- Phase 1.5: Data Center Overlay --
    dc_locations = []
    dc_summary = {}

    if dc_scrape:
        log.info("Phase 1.5: Data Center Scrape")
        try:
            from scraping.dc_scraper import (
                load_dc_config,
                scrape_state_listings,
                scrape_detail_pages,
                combine_dc_data,
                build_dc_summary,
            )
            from scraping.geocoder import geocode_single

            dc_config = load_dc_config(iso_id)
            dc_cache_dir = data_dir / iso_id / "data_centers"

            dc_listings = scrape_state_listings(
                states=dc_config.get("states", []),
                cache_path=dc_cache_dir / "dc_state_listings.json",
                force=False,
            )
            dc_details = scrape_detail_pages(
                listings=dc_listings,
                cache_path=dc_cache_dir / "dc_details.json",
                force=False,
            )
            dc_records = combine_dc_data(
                listings=dc_listings,
                details=dc_details,
                operator_to_zone=dc_config.get("operator_to_zone", {}),
                operator_substring_map=dc_config.get("operator_substring_map", {}),
                cache_path=dc_cache_dir / "dc_combined.json",
            )
            dc_summary = build_dc_summary(dc_records, zone_key="iso_zone")
            log.info(f"Data centers: {len(dc_records)} {iso_id.upper()} records")

            # Store zone translation mapping if present in DC config
            dc_zone_mapping = dc_config.get("dc_zone_to_cls_zones", {})
            if dc_zone_mapping:
                dc_summary["dc_zone_to_cls_zones"] = dc_zone_mapping

            # Convert to map-format locations
            zone_centroid_map = dc_config.get("zone_centroids", {})
            for rec in dc_records:
                zone = rec.get("iso_zone", "")
                centroid = zone_centroid_map.get(zone, [39.5, -78.0])
                lat = centroid[0] if isinstance(centroid, list) else centroid
                lon = centroid[1] if isinstance(centroid, list) else centroid
                dc_locations.append({
                    "name": rec.get("facility_name", ""),
                    "lat": lat,
                    "lon": lon,
                    "zone": zone,
                    "status": rec.get("status", ""),
                    "capacity": rec.get("capacity", ""),
                    "capacity_mw": rec.get("capacity_mw", 0),
                    "county": rec.get("county", ""),
                    "state_code": rec.get("state_code", ""),
                    "operator": rec.get("operator", ""),
                })
        except Exception as e:
            log.warning(f"DC scraping failed: {e}")
    else:
        # Try loading cached DC data
        dc_combined_path = data_dir / iso_id / "data_centers" / "dc_combined.json"
        if dc_combined_path.exists():
            try:
                with open(dc_combined_path) as f:
                    dc_records = json.load(f)
                from scraping.dc_scraper import build_dc_summary, load_dc_config
                dc_summary = build_dc_summary(dc_records, zone_key="iso_zone")
                # Load zone translation mapping from DC config
                try:
                    cached_dc_config = load_dc_config(iso_id)
                    cached_zone_mapping = cached_dc_config.get("dc_zone_to_cls_zones", {})
                    if cached_zone_mapping:
                        dc_summary["dc_zone_to_cls_zones"] = cached_zone_mapping
                except Exception:
                    pass
                log.info(f"Loaded {len(dc_records)} cached DC records")
            except Exception:
                pass

    # -- Phase 2: Constraint Classification --
    log.info("")
    log.info("Phase 2: Constraint Classification")

    metrics_df = compute_zone_metrics(
        zone_lmps,
        peak_hours=config.peak_hours,
        rto_aggregates=config.rto_aggregates,
    )
    log.info(f"Computed metrics for {len(metrics_df)} zones")

    classification_df = classify_zones(
        metrics_df,
        validation_zones=config.validation_zones,
    )

    # Log congestion approximation warning for ERCOT
    if config.congestion_approximated:
        log.warning(
            f"{iso_id.upper()}: congestion values are APPROXIMATED "
            f"(zone LMP - hub average). No LMP decomposition available."
        )

    log.info("")
    log.info("Classification Summary:")
    log.info("-" * 70)
    for _, row in classification_df.sort_values("transmission_score", ascending=False).iterrows():
        log.info(
            f"  {row['zone']:10s} | {row['classification']:15s} | "
            f"T={row['transmission_score']:.3f} G={row['generation_score']:.3f} | "
            f"Cong=${row['avg_abs_congestion']:.2f}/MWh"
        )

    # Write classifications to DB
    if db_writer:
        db_writer.write_zone_lmp_count(len(zone_lmps))
        db_writer.write_classifications(classification_df)

    # -- Phase 2.5: Pnode Drill-Down --
    pnode_results = {}
    pnode_coordinates = {}

    if pnode_drilldown and config.has_node_level_pricing:
        log.info("")
        log.info("Phase 2.5: Pnode Congestion Drill-Down")

        interim_scores = []
        for _, row in classification_df.iterrows():
            interim_scores.append({
                "zone": row["zone"],
                "transmission_score": row["transmission_score"],
                "generation_score": row["generation_score"],
            })
        interim_summary = {"zone_scores": interim_scores}

        zone_data = adapter.pull_constrained_zone_pnodes(
            interim_summary, year=year, force=False,
        )

        pnode_cache = data_dir / iso_id / "pnodes" / "pnode_drilldown_results.json"
        pnode_results = analyze_all_constrained_zones(
            zone_data, cache_path=pnode_cache, peak_hours=config.peak_hours,
        )
        log.info(f"Pnode drill-down: {len(pnode_results)} zones analyzed")

        # Geocode pnode names
        try:
            from scraping.geocoder import geocode_pnodes
            geo_cache = data_dir / iso_id / "geo" / "pnode_coordinates.json"
            pnode_coordinates = geocode_pnodes(
                pnode_results=pnode_results,
                zone_state_map=config.zone_state_map,
                zone_centroids=zone_centroids,
                cache_path=geo_cache,
            )
            log.info(f"Pnode coordinates: {len(pnode_coordinates)} names resolved")
        except Exception as e:
            log.warning(f"Pnode geocoding failed: {e}")

    elif pnode_drilldown and not config.has_node_level_pricing:
        log.info(
            f"{iso_id.upper()}: node-level pricing not available, "
            f"skipping pnode drill-down"
        )
    else:
        # Try loading cached pnode results
        pnode_cache = data_dir / iso_id / "pnodes" / "pnode_drilldown_results.json"
        pnode_results = load_pnode_results(pnode_cache)
        if pnode_results:
            log.info(f"Loaded cached pnode data: {len(pnode_results)} zones")

    # -- Phase 3: DER Recommendations --
    log.info("")
    log.info("Phase 3: DER Recommendations")

    recommendations = recommend_ders(classification_df, zone_lmps)

    for rec in recommendations:
        log.info("")
        log.info(format_recommendation_text(rec))

    # Write recommendations to DB
    if db_writer:
        db_writer.write_recommendations(recommendations)

    # -- Phase 4: Visualization --
    log.info("")
    log.info("Phase 4: Visualization")

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
        backbone_geojson=backbone_geojson,
        output_path=output_dir / "grid_constraint_map.html",
        map_center=config.map_center,
        map_zoom=config.map_zoom,
        iso_name=config.iso_name,
        zone_key=zone_key,
    )

    try:
        create_score_bar_chart(
            classification_df,
            output_path=output_dir / "score_comparison.png",
            iso_name=config.iso_name,
        )
        create_congestion_heatmap(
            zone_lmps,
            output_path=output_dir / "congestion_heatmap.png",
            rto_aggregates=config.rto_aggregates,
            iso_name=config.iso_name,
        )
        create_monthly_trend_chart(
            zone_lmps,
            output_path=output_dir / "monthly_congestion_trends.png",
            rto_aggregates=config.rto_aggregates,
            iso_name=config.iso_name,
        )
    except Exception as e:
        log.warning(f"Chart generation failed (non-fatal): {e}")

    # -- Phase 5: Export Summary --
    log.info("")
    log.info("Phase 5: Export Summary")

    summary = {
        "metadata": {
            "iso_id": iso_id,
            "iso_name": config.iso_name,
            "year": year,
            "total_zone_lmp_rows": len(zone_lmps),
            "zones_analyzed": len(classification_df),
            "has_lmp_decomposition": config.has_lmp_decomposition,
            "has_node_level_pricing": config.has_node_level_pricing,
            "congestion_approximated": config.congestion_approximated,
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

    summary["distribution"] = classification_df["classification"].value_counts().to_dict()

    if pnode_results:
        summary["pnode_drilldown"] = pnode_results

    if dc_summary:
        # Build dynamic zone mapping for SPP (settlement locations -> DC zones)
        if iso_id == "spp" and "dc_zone_to_cls_zones" not in dc_summary:
            dc_config_path = PROJECT_ROOT / "scraping" / "dc_configs" / "spp.yaml"
            if dc_config_path.exists():
                import yaml
                with open(dc_config_path) as f:
                    spp_dc_config = yaml.safe_load(f)
                all_cls_zones = [zs["zone"] for zs in summary["zone_scores"]]
                spp_dc_zones = list(set(
                    z for z in (spp_dc_config.get("operator_to_zone", {}).values())
                    if z
                ))
                dc_zone_mapping = {}
                # Apply static overrides first (e.g. AEPW -> CSWS prefix)
                static_map = spp_dc_config.get("dc_zone_to_cls_zones_static", {})
                for dc_zone in spp_dc_zones:
                    prefix = static_map.get(dc_zone, dc_zone)
                    matched = [z for z in all_cls_zones
                               if z.startswith(prefix + ".") or z.startswith(prefix + "_") or z == prefix]
                    if matched:
                        dc_zone_mapping[dc_zone] = matched
                if dc_zone_mapping:
                    dc_summary["dc_zone_to_cls_zones"] = dc_zone_mapping
                    log.info(f"SPP dynamic zone mapping: {len(dc_zone_mapping)} DC zones mapped")

        summary["data_centers"] = dc_summary

    # Compute zone-level 12x24 congestion heatmaps
    zone_heatmaps = {}
    for zone in classification_df["zone"]:
        zdf = zone_lmps[zone_lmps["pnode_name"] == zone]
        if zdf.empty:
            continue
        pivot = zdf.pivot_table(
            values="congestion_price_da",
            index="month",
            columns="hour",
            aggfunc=lambda x: x.abs().mean(),
        ).reindex(index=range(1, 13), columns=range(24), fill_value=0.0)
        zone_heatmaps[zone] = {
            "data": {str(m): pivot.loc[m].round(2).tolist() for m in range(1, 13)},
            "max_congestion": round(float(pivot.values.max()), 2),
        }
    if zone_heatmaps:
        summary["zone_heatmaps"] = zone_heatmaps
        log.info(f"Computed 12x24 congestion heatmaps for {len(zone_heatmaps)} zones")

    summary_path = output_dir / "classification_summary.json"
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)
    log.info(f"Exported summary to {summary_path}")

    # Write pnode scores to DB
    if db_writer and pnode_results:
        db_writer.write_pnode_scores(pnode_results)

    # Mark pipeline run as complete
    if db_writer:
        db_writer.complete_run()
        db_writer.close()

    # -- Done --
    log.info("")
    log.info("=" * 60)
    log.info(f"Pipeline complete for {iso_id.upper()}!")
    log.info(f"  Map:     {map_path}")
    log.info(f"  Summary: {summary_path}")
    log.info(f"  Charts:  {output_dir}/")
    log.info("=" * 60)

    return summary


def run_all_isos(year: int = 2025, **kwargs) -> dict:
    """Run pipeline for all supported ISOs."""
    results = {}
    for iso_id in SUPPORTED_ISOS:
        try:
            results[iso_id] = run_single_iso(iso_id=iso_id, year=year, **kwargs)
        except Exception as e:
            logger.error(f"Pipeline failed for {iso_id}: {e}")
            results[iso_id] = {"error": str(e)}
    return results


def main():
    parser = argparse.ArgumentParser(
        description="Multi-ISO Grid Constraint -> DER Mapping Pipeline"
    )
    parser.add_argument(
        "--iso",
        type=str,
        default="pjm",
        help=f"ISO to run (default: pjm). Options: {', '.join(SUPPORTED_ISOS)}, all",
    )
    parser.add_argument(
        "--year", type=int, default=2025,
        help="Year for LMP data (default: 2025)",
    )
    parser.add_argument(
        "--skip-download", action="store_true",
        help="Use cached data only",
    )
    parser.add_argument(
        "--pnode-drilldown", action="store_true",
        help="Run pnode congestion hotspot analysis for constrained zones",
    )
    parser.add_argument(
        "--dc-scrape", action="store_true",
        help="Scrape data center listings from interconnection.fyi",
    )
    parser.add_argument(
        "--list-isos", action="store_true",
        help="List supported ISOs and exit",
    )

    args = parser.parse_args()

    if args.list_isos:
        print("Supported ISOs:")
        for iso_id in SUPPORTED_ISOS:
            try:
                adapter = get_adapter(iso_id)
                config = adapter.config
                flags = []
                if not config.has_lmp_decomposition:
                    flags.append("no decomposition")
                if not config.has_node_level_pricing:
                    flags.append("no node pricing")
                if config.congestion_approximated:
                    flags.append("congestion approximated")
                flag_str = f" ({', '.join(flags)})" if flags else ""
                print(f"  {iso_id:8s} - {config.iso_name}{flag_str}")
            except Exception as e:
                print(f"  {iso_id:8s} - error loading: {e}")
        return

    iso_id = args.iso.lower()

    if iso_id == "all":
        run_all_isos(
            year=args.year,
            skip_download=args.skip_download,
            pnode_drilldown=args.pnode_drilldown,
            dc_scrape=args.dc_scrape,
        )
    else:
        if iso_id not in SUPPORTED_ISOS:
            print(f"Unknown ISO: '{iso_id}'. Supported: {', '.join(SUPPORTED_ISOS)}, all")
            sys.exit(1)
        run_single_iso(
            iso_id=iso_id,
            year=args.year,
            skip_download=args.skip_download,
            pnode_drilldown=args.pnode_drilldown,
            dc_scrape=args.dc_scrape,
        )


if __name__ == "__main__":
    main()
