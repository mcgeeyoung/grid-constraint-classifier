#!/usr/bin/env python3
"""
Migrate existing file-based pipeline results into the database.

Reads classification_summary.json, parquet files, and DC records
from the output/ and data/ directories and populates the DB tables.

Usage:
  python -m cli.migrate_data --iso pjm
  python -m cli.migrate_data --iso all
"""

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy.orm import Session

from app.database import engine, SessionLocal
from app.models import (
    Base, ISO, Zone, ZoneLMP, PipelineRun,
    ZoneClassification, Pnode, PnodeScore,
    DataCenter, DERRecommendation,
)
from adapters.registry import get_adapter, SUPPORTED_ISOS

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"
OUTPUT_DIR = PROJECT_ROOT / "output"


def ensure_tables():
    """Create all tables if they don't exist."""
    Base.metadata.create_all(engine)
    logger.info("Database tables ensured")


def migrate_iso(iso_id: str, db: Session):
    """Migrate data for a single ISO into the database."""
    logger.info(f"Migrating {iso_id}...")

    # Load adapter config
    adapter = get_adapter(iso_id, data_dir=DATA_DIR)
    config = adapter.config

    # Upsert ISO
    iso = db.query(ISO).filter(ISO.iso_code == iso_id).first()
    if not iso:
        iso = ISO(
            iso_code=iso_id,
            iso_name=config.iso_name,
            timezone=config.timezone,
            has_decomposition=config.has_lmp_decomposition,
            has_node_pricing=config.has_node_level_pricing,
        )
        db.add(iso)
        db.flush()
        logger.info(f"  Created ISO: {iso_id}")
    else:
        logger.info(f"  ISO exists: {iso_id}")

    # Upsert zones
    zone_lookup = {}
    for zone_code, zinfo in config.zones.items():
        zone = db.query(Zone).filter(
            Zone.iso_id == iso.id, Zone.zone_code == zone_code
        ).first()
        if not zone:
            zone = Zone(
                iso_id=iso.id,
                zone_code=zone_code,
                zone_name=zinfo.get("name", zone_code),
                centroid_lat=zinfo.get("centroid_lat"),
                centroid_lon=zinfo.get("centroid_lon"),
                states=zinfo.get("states", []),
            )
            db.add(zone)
            db.flush()
        zone_lookup[zone_code] = zone

    logger.info(f"  Zones: {len(zone_lookup)}")

    # Load classification summary if available
    # Check both output/{iso_id}/classification_summary.json and output/classification_summary.json
    summary_path = OUTPUT_DIR / iso_id / "classification_summary.json"
    if not summary_path.exists():
        summary_path = OUTPUT_DIR / "classification_summary.json"
    if not summary_path.exists():
        logger.info(f"  No classification summary found, skipping")
        db.commit()
        return

    with open(summary_path) as f:
        summary = json.load(f)

    year = summary.get("metadata", {}).get("year", 2025)

    # Create pipeline run
    run = PipelineRun(
        iso_id=iso.id,
        year=year,
        started_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
        status="completed",
        zone_lmp_rows=summary.get("metadata", {}).get("total_zone_lmp_rows", 0),
    )
    db.add(run)
    db.flush()
    logger.info(f"  Created pipeline run #{run.id} (year={year})")

    # Migrate zone classifications
    zone_scores = summary.get("zone_scores", [])
    cls_count = 0
    for zs in zone_scores:
        zone_code = zs["zone"]
        zone = zone_lookup.get(zone_code)
        if not zone:
            continue

        cls = ZoneClassification(
            pipeline_run_id=run.id,
            zone_id=zone.id,
            classification=zs["classification"],
            transmission_score=zs["transmission_score"],
            generation_score=zs["generation_score"],
            avg_abs_congestion=zs.get("avg_abs_congestion"),
            max_congestion=zs.get("max_congestion"),
            congested_hours_pct=zs.get("congested_hours_pct"),
        )
        db.add(cls)
        cls_count += 1

    logger.info(f"  Zone classifications: {cls_count}")

    # Migrate pnode drill-down results
    pnode_drilldown = summary.get("pnode_drilldown", {})
    pnode_count = 0
    for zone_code, analysis in pnode_drilldown.items():
        zone = zone_lookup.get(zone_code)
        if not zone:
            continue

        for pdata in analysis.get("all_scored", []):
            # Upsert pnode
            ext_id = str(pdata.get("pnode_id", pdata["pnode_name"]))
            pnode = db.query(Pnode).filter(
                Pnode.iso_id == iso.id,
                Pnode.node_id_external == ext_id,
            ).first()
            if not pnode:
                pnode = Pnode(
                    iso_id=iso.id,
                    zone_id=zone.id,
                    node_id_external=ext_id,
                    node_name=pdata["pnode_name"],
                )
                db.add(pnode)
                db.flush()

            score = PnodeScore(
                pipeline_run_id=run.id,
                pnode_id=pnode.id,
                severity_score=pdata["severity_score"],
                tier=pdata["tier"],
                avg_congestion=pdata.get("avg_congestion"),
                max_congestion=pdata.get("max_congestion"),
                congested_hours_pct=pdata.get("congested_hours_pct"),
                constraint_loadshape=pdata.get("constraint_loadshape"),
            )
            db.add(score)
            pnode_count += 1

    logger.info(f"  Pnode scores: {pnode_count}")

    # Migrate DER recommendations
    recommendations = summary.get("recommendations", [])
    rec_count = 0
    for rec in recommendations:
        zone_code = rec.get("zone")
        zone = zone_lookup.get(zone_code)
        if not zone:
            continue

        der_rec = DERRecommendation(
            pipeline_run_id=run.id,
            zone_id=zone.id,
            classification=rec.get("classification"),
            rationale=rec.get("rationale"),
            congestion_value=rec.get("congestion_value_annual"),
            primary_rec=rec.get("primary_recommendation"),
            secondary_rec=rec.get("secondary_recommendation"),
            tertiary_rec=rec.get("tertiary_recommendation"),
        )
        db.add(der_rec)
        rec_count += 1

    logger.info(f"  DER recommendations: {rec_count}")

    # Migrate data centers
    dc_data = summary.get("data_centers", {})
    dc_combined_path = DATA_DIR / iso_id / "data_centers" / "dc_combined.json"
    if not dc_combined_path.exists():
        dc_combined_path = DATA_DIR / "data_centers" / "dc_combined.json"

    dc_count = 0
    if dc_combined_path.exists():
        with open(dc_combined_path) as f:
            dc_records = json.load(f)

        for dc in dc_records:
            slug = dc.get("slug", "")
            if not slug:
                continue

            existing = db.query(DataCenter).filter(
                DataCenter.external_slug == slug
            ).first()
            if existing:
                continue

            zone_code = dc.get("iso_zone") or dc.get("pjm_zone", "")
            zone = zone_lookup.get(zone_code)

            data_center = DataCenter(
                iso_id=iso.id,
                zone_id=zone.id if zone else None,
                external_slug=slug,
                facility_name=dc.get("facility_name"),
                status=dc.get("status"),
                capacity_mw=dc.get("capacity_mw"),
                state_code=dc.get("state_code"),
                county=dc.get("county"),
                operator=dc.get("operator"),
                scraped_at=datetime.now(timezone.utc),
            )
            db.add(data_center)
            dc_count += 1

        logger.info(f"  Data centers: {dc_count}")

    db.commit()
    logger.info(f"  Migration complete for {iso_id}")


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    parser = argparse.ArgumentParser(description="Migrate file-based data to database")
    parser.add_argument(
        "--iso", type=str, default="pjm",
        help=f"ISO to migrate (default: pjm). Options: {', '.join(SUPPORTED_ISOS)}, all",
    )
    parser.add_argument(
        "--create-tables", action="store_true",
        help="Create database tables before migrating",
    )

    args = parser.parse_args()

    if args.create_tables:
        ensure_tables()

    db = SessionLocal()
    try:
        if args.iso.lower() == "all":
            for iso_id in SUPPORTED_ISOS:
                try:
                    migrate_iso(iso_id, db)
                except Exception as e:
                    logger.error(f"Migration failed for {iso_id}: {e}")
                    db.rollback()
        else:
            migrate_iso(args.iso.lower(), db)
    finally:
        db.close()


if __name__ == "__main__":
    main()
