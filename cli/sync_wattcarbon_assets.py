#!/usr/bin/env python3
"""
Sync WattCarbon enrolled assets into DERLocation records.

Pulls all assets from the WattCarbon API, geo-resolves each into the
grid hierarchy, and upserts DERLocation records with source="wattcarbon".

Usage:
  python -m cli.sync_wattcarbon_assets                    # Sync all active assets
  python -m cli.sync_wattcarbon_assets --dry-run           # Preview without writing
  python -m cli.sync_wattcarbon_assets --status active      # Filter by status
  python -m cli.sync_wattcarbon_assets --force              # Re-resolve existing records
"""

import argparse
import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from adapters.wattcarbon_client import WattCarbonClient
from app.database import SessionLocal
from app.models import DERLocation
from core.der_profiles import WATTCARBON_KIND_MAP, get_eac_category
from core.geo_resolver import resolve

logger = logging.getLogger(__name__)


def sync_assets(
    status: str | None = None,
    dry_run: bool = False,
    force: bool = False,
) -> dict:
    """Pull WattCarbon assets and upsert DERLocation records.

    Args:
        status: Only sync assets with this status (e.g. "active").
        dry_run: If True, log what would happen without writing to DB.
        force: If True, re-resolve geo hierarchy for existing records.

    Returns:
        Summary dict with created/updated/skipped counts.
    """
    client = WattCarbonClient()
    assets = client.list_assets(status=status)

    logger.info(f"Fetched {len(assets)} assets from WattCarbon API")

    if dry_run:
        logger.info("DRY RUN: no database changes will be made")

    db = SessionLocal()
    created = 0
    updated = 0
    skipped = 0

    try:
        for asset in assets:
            asset_id = str(asset.get("id", ""))
            kind = asset.get("kind", "")
            lat = asset.get("lat") or asset.get("latitude")
            lon = asset.get("lon") or asset.get("longitude")
            nameplate_kw = asset.get("nameplateCapacityKw") or asset.get("nameplate_capacity_kw", 0)

            # Skip assets without coordinates
            if not lat or not lon:
                logger.debug(f"  Skipping asset {asset_id} ({kind}): no coordinates")
                skipped += 1
                continue

            # Map WattCarbon kind to internal der_type
            der_type = WATTCARBON_KIND_MAP.get(kind)
            if not der_type:
                logger.debug(f"  Skipping asset {asset_id}: unknown kind {kind!r}")
                skipped += 1
                continue

            capacity_mw = float(nameplate_kw) / 1000.0
            if capacity_mw <= 0:
                logger.debug(f"  Skipping asset {asset_id}: zero capacity")
                skipped += 1
                continue

            if dry_run:
                logger.info(
                    f"  [DRY RUN] Would sync asset {asset_id}: "
                    f"{kind} -> {der_type}, {capacity_mw:.3f} MW, "
                    f"({lat:.4f}, {lon:.4f})"
                )
                created += 1
                continue

            # Check for existing record
            existing = (
                db.query(DERLocation)
                .filter(DERLocation.wattcarbon_asset_id == asset_id)
                .first()
            )

            if existing and not force:
                logger.debug(f"  Asset {asset_id} already synced (DERLocation #{existing.id})")
                skipped += 1
                continue

            # Geo-resolve
            resolution = resolve(db, float(lat), float(lon))
            if not resolution.iso_id:
                logger.warning(
                    f"  Asset {asset_id}: could not resolve ({lat}, {lon}) to any ISO"
                )
                skipped += 1
                continue

            eac_category = get_eac_category(der_type)

            if existing and force:
                # Update existing record with fresh geo-resolution
                existing.iso_id = resolution.iso_id
                existing.zone_id = resolution.zone_id
                existing.substation_id = resolution.substation_id
                existing.feeder_id = resolution.feeder_id
                existing.circuit_id = resolution.circuit_id
                existing.nearest_pnode_id = resolution.nearest_pnode_id
                existing.der_type = der_type
                existing.eac_category = eac_category
                existing.capacity_mw = capacity_mw
                existing.lat = float(lat)
                existing.lon = float(lon)
                updated += 1
                logger.info(
                    f"  Updated asset {asset_id}: {der_type}, {capacity_mw:.3f} MW "
                    f"-> {resolution.iso_code}/{resolution.zone_code} "
                    f"(depth={resolution.resolution_depth})"
                )
            else:
                # Create new record
                location = DERLocation(
                    iso_id=resolution.iso_id,
                    zone_id=resolution.zone_id,
                    substation_id=resolution.substation_id,
                    feeder_id=resolution.feeder_id,
                    circuit_id=resolution.circuit_id,
                    nearest_pnode_id=resolution.nearest_pnode_id,
                    der_type=der_type,
                    eac_category=eac_category,
                    capacity_mw=capacity_mw,
                    lat=float(lat),
                    lon=float(lon),
                    wattcarbon_asset_id=asset_id,
                    source="wattcarbon",
                )
                db.add(location)
                created += 1
                logger.info(
                    f"  Created asset {asset_id}: {der_type}, {capacity_mw:.3f} MW "
                    f"-> {resolution.iso_code}/{resolution.zone_code} "
                    f"(depth={resolution.resolution_depth})"
                )

        if not dry_run:
            db.commit()
            logger.info("Committed all changes to database")

    except Exception as e:
        db.rollback()
        logger.error(f"Sync failed: {e}")
        raise
    finally:
        db.close()

    summary = {
        "total_fetched": len(assets),
        "created": created,
        "updated": updated,
        "skipped": skipped,
    }

    logger.info(
        f"Sync complete: {summary['created']} created, "
        f"{summary['updated']} updated, {summary['skipped']} skipped "
        f"(of {summary['total_fetched']} total)"
    )
    return summary


def main():
    parser = argparse.ArgumentParser(
        description="Sync WattCarbon assets into DERLocation records"
    )
    parser.add_argument(
        "--status",
        type=str,
        default=None,
        help="Filter assets by status (e.g. 'active')",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview sync without writing to database",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-resolve geo hierarchy for existing records",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable debug logging",
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )

    sync_assets(
        status=args.status,
        dry_run=args.dry_run,
        force=args.force,
    )


if __name__ == "__main__":
    main()
