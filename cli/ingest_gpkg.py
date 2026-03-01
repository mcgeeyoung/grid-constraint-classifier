"""CLI tool to load priority layers from USA.gpkg into PostGIS.

Loads three priority layers:
  - power_line      (538K features) -> gpkg_power_lines
  - power_substation_polygon (68K)  -> gpkg_substations
  - power_plant     (15K features)  -> gpkg_power_plants

Unit normalization on ingest:
  - Voltage: volts -> kV  (divide by 1000)
  - Output:  watts -> MW  (divide by 1_000_000)

Usage:
    python -m cli.ingest_gpkg path/to/USA.gpkg                 # Load all 3 layers
    python -m cli.ingest_gpkg path/to/USA.gpkg --layer lines   # Load only power lines
    python -m cli.ingest_gpkg path/to/USA.gpkg --layer subs    # Load only substations
    python -m cli.ingest_gpkg path/to/USA.gpkg --layer plants  # Load only power plants
    python -m cli.ingest_gpkg path/to/USA.gpkg --dry-run       # Count features without loading
    python -m cli.ingest_gpkg path/to/USA.gpkg --clear         # Clear tables before loading
"""

import argparse
import logging
import sqlite3
import struct
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shapely import wkb
from sqlalchemy import text, inspect

from app.database import SessionLocal, engine
from app.models.gpkg import GPKGPowerLine, GPKGSubstation, GPKGPowerPlant

# Check if PostGIS geom columns exist in the DB
_inspector = inspect(engine)
_has_geom = {
    "gpkg_power_lines": "geom" in [c["name"] for c in _inspector.get_columns("gpkg_power_lines")],
    "gpkg_substations": "geom" in [c["name"] for c in _inspector.get_columns("gpkg_substations")],
    "gpkg_power_plants": "geom" in [c["name"] for c in _inspector.get_columns("gpkg_power_plants")],
}

if any(_has_geom.values()):
    from geoalchemy2.shape import from_shape

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(message)s",
)
log = logging.getLogger(__name__)

BATCH_SIZE = 2000


# ── Geometry Conversion ──────────────────────────────────────────────

def gpkg_blob_to_shapely(blob: bytes):
    """Convert GeoPackage geometry binary to a Shapely geometry.

    GeoPackage binary format:
      - 2 bytes: magic "GP"
      - 1 byte: version
      - 1 byte: flags (bits 1-3 = envelope type)
      - 4 bytes: SRS ID
      - variable: envelope (depends on type)
      - remainder: WKB geometry
    """
    if blob is None or len(blob) < 8:
        return None

    # Validate magic bytes
    if blob[0:2] != b"GP":
        return None

    flags = blob[3]
    envelope_type = (flags >> 1) & 0x07
    envelope_sizes = [0, 32, 48, 48, 64]
    if envelope_type >= len(envelope_sizes):
        return None

    header_len = 8 + envelope_sizes[envelope_type]
    wkb_bytes = blob[header_len:]

    if len(wkb_bytes) < 5:
        return None

    try:
        return wkb.loads(wkb_bytes)
    except Exception:
        return None


def voltage_to_kv(volts: float | None) -> float | None:
    """Convert volts to kV. Returns None if input is None."""
    if volts is None:
        return None
    return round(volts / 1000.0, 2)


def watts_to_mw(watts: float | None) -> float | None:
    """Convert watts to MW. Returns None if input is None."""
    if watts is None:
        return None
    return round(watts / 1_000_000.0, 3)


# ── Layer Loaders ────────────────────────────────────────────────────

def load_power_lines(gpkg_path: str, session, clear: bool = False):
    """Load power_line layer into gpkg_power_lines table."""
    if clear:
        count = session.query(GPKGPowerLine).delete()
        session.commit()
        log.info("Cleared %d existing power line records", count)

    conn = sqlite3.connect(gpkg_path)
    total = conn.execute("SELECT COUNT(*) FROM power_line").fetchone()[0]
    log.info("Loading %d power lines...", total)

    cursor = conn.execute(
        "SELECT fid, geometry, id, name, ref, operator, max_voltage, "
        "voltages, circuits, cables, location, construction, disused, "
        "frequency, start_date FROM power_line"
    )

    batch = []
    loaded = 0
    skipped = 0
    t0 = time.time()

    for row in cursor:
        fid, geom_blob, osm_id, name, ref, operator, max_voltage, \
            voltages, circuits, cables, location, construction, disused, \
            frequency, start_date = row

        geom = gpkg_blob_to_shapely(geom_blob)
        if geom is None:
            skipped += 1
            continue

        kwargs = dict(
            osm_id=osm_id,
            name=name[:300] if name else None,
            ref=ref[:100] if ref else None,
            operator=operator[:300] if operator else None,
            max_voltage_kv=voltage_to_kv(max_voltage),
            voltages=voltages[:200] if voltages else None,
            circuits=circuits,
            cables=cables[:50] if cables else None,
            location=location[:50] if location else None,
            construction=bool(construction) if construction is not None else None,
            disused=bool(disused) if disused is not None else None,
            frequency=frequency[:50] if frequency else None,
            start_date=start_date[:50] if start_date else None,
        )
        if _has_geom["gpkg_power_lines"]:
            kwargs["geom"] = from_shape(geom, srid=4326)
        record = GPKGPowerLine(**kwargs)
        batch.append(record)

        if len(batch) >= BATCH_SIZE:
            session.bulk_save_objects(batch)
            session.commit()
            loaded += len(batch)
            elapsed = time.time() - t0
            rate = loaded / elapsed if elapsed > 0 else 0
            log.info(
                "  power_lines: %d/%d (%.0f/sec, %d skipped)",
                loaded, total, rate, skipped,
            )
            batch = []

    if batch:
        session.bulk_save_objects(batch)
        session.commit()
        loaded += len(batch)

    elapsed = time.time() - t0
    conn.close()
    log.info(
        "Power lines complete: %d loaded, %d skipped, %.1fs",
        loaded, skipped, elapsed,
    )
    return loaded


def load_substations(gpkg_path: str, session, clear: bool = False):
    """Load power_substation_polygon layer into gpkg_substations table."""
    if clear:
        count = session.query(GPKGSubstation).delete()
        session.commit()
        log.info("Cleared %d existing substation records", count)

    conn = sqlite3.connect(gpkg_path)
    total = conn.execute(
        "SELECT COUNT(*) FROM power_substation_polygon"
    ).fetchone()[0]
    log.info("Loading %d substations...", total)

    cursor = conn.execute(
        "SELECT fid, geometry, id, name, ref, operator, substation_type, "
        "max_voltage, voltages, frequency, construction, start_date "
        "FROM power_substation_polygon"
    )

    batch = []
    loaded = 0
    skipped = 0
    t0 = time.time()

    for row in cursor:
        fid, geom_blob, osm_id, name, ref, operator, sub_type, \
            max_voltage, voltages, frequency, construction, start_date = row

        geom = gpkg_blob_to_shapely(geom_blob)
        if geom is None:
            skipped += 1
            continue

        # Compute centroid for point queries
        centroid = geom.centroid
        centroid_lat = round(centroid.y, 6) if centroid else None
        centroid_lon = round(centroid.x, 6) if centroid else None

        kwargs = dict(
            osm_id=osm_id,
            name=name[:300] if name else None,
            ref=ref[:100] if ref else None,
            operator=operator[:300] if operator else None,
            substation_type=sub_type[:100] if sub_type else None,
            max_voltage_kv=voltage_to_kv(max_voltage),
            voltages=voltages[:200] if voltages else None,
            frequency=frequency[:50] if frequency else None,
            construction=bool(construction) if construction is not None else None,
            start_date=start_date[:50] if start_date else None,
            centroid_lat=centroid_lat,
            centroid_lon=centroid_lon,
        )
        if _has_geom["gpkg_substations"]:
            kwargs["geom"] = from_shape(geom, srid=4326)
        record = GPKGSubstation(**kwargs)
        batch.append(record)

        if len(batch) >= BATCH_SIZE:
            session.bulk_save_objects(batch)
            session.commit()
            loaded += len(batch)
            elapsed = time.time() - t0
            rate = loaded / elapsed if elapsed > 0 else 0
            log.info(
                "  substations: %d/%d (%.0f/sec, %d skipped)",
                loaded, total, rate, skipped,
            )
            batch = []

    if batch:
        session.bulk_save_objects(batch)
        session.commit()
        loaded += len(batch)

    elapsed = time.time() - t0
    conn.close()
    log.info(
        "Substations complete: %d loaded, %d skipped, %.1fs",
        loaded, skipped, elapsed,
    )
    return loaded


def load_power_plants(gpkg_path: str, session, clear: bool = False):
    """Load power_plant layer into gpkg_power_plants table."""
    if clear:
        count = session.query(GPKGPowerPlant).delete()
        session.commit()
        log.info("Cleared %d existing power plant records", count)

    conn = sqlite3.connect(gpkg_path)
    total = conn.execute("SELECT COUNT(*) FROM power_plant").fetchone()[0]
    log.info("Loading %d power plants...", total)

    cursor = conn.execute(
        "SELECT fid, geometry, id, name, wikidata, operator, source, "
        "method, output, construction, start_date FROM power_plant"
    )

    batch = []
    loaded = 0
    skipped = 0
    t0 = time.time()

    for row in cursor:
        fid, geom_blob, osm_id, name, wikidata, operator, source, \
            method, output_watts, construction, start_date = row

        geom = gpkg_blob_to_shapely(geom_blob)
        if geom is None:
            skipped += 1
            continue

        # Compute centroid for point queries
        centroid = geom.centroid
        centroid_lat = round(centroid.y, 6) if centroid else None
        centroid_lon = round(centroid.x, 6) if centroid else None

        kwargs = dict(
            osm_id=osm_id,
            name=name[:300] if name else None,
            wikidata=wikidata[:50] if wikidata else None,
            operator=operator[:300] if operator else None,
            source=source[:100] if source else None,
            method=method[:100] if method else None,
            output_mw=watts_to_mw(output_watts),
            construction=bool(construction) if construction is not None else None,
            start_date=start_date[:50] if start_date else None,
            centroid_lat=centroid_lat,
            centroid_lon=centroid_lon,
        )
        if _has_geom["gpkg_power_plants"]:
            kwargs["geom"] = from_shape(geom, srid=4326)
        record = GPKGPowerPlant(**kwargs)
        batch.append(record)

        if len(batch) >= BATCH_SIZE:
            session.bulk_save_objects(batch)
            session.commit()
            loaded += len(batch)
            elapsed = time.time() - t0
            rate = loaded / elapsed if elapsed > 0 else 0
            log.info(
                "  power_plants: %d/%d (%.0f/sec, %d skipped)",
                loaded, total, rate, skipped,
            )
            batch = []

    if batch:
        session.bulk_save_objects(batch)
        session.commit()
        loaded += len(batch)

    elapsed = time.time() - t0
    conn.close()
    log.info(
        "Power plants complete: %d loaded, %d skipped, %.1fs",
        loaded, skipped, elapsed,
    )
    return loaded


# ── Dry Run ──────────────────────────────────────────────────────────

def dry_run(gpkg_path: str):
    """Count features in each priority layer without loading."""
    conn = sqlite3.connect(gpkg_path)

    layers = [
        ("power_line", "gpkg_power_lines"),
        ("power_substation_polygon", "gpkg_substations"),
        ("power_plant", "gpkg_power_plants"),
    ]

    log.info("Dry run: counting features in %s", gpkg_path)
    for gpkg_layer, table in layers:
        total = conn.execute(f"SELECT COUNT(*) FROM {gpkg_layer}").fetchone()[0]
        null_geom = conn.execute(
            f"SELECT COUNT(*) FROM {gpkg_layer} WHERE geometry IS NULL"
        ).fetchone()[0]
        log.info(
            "  %-35s %7d features (%d null geom) -> %s",
            gpkg_layer, total, null_geom, table,
        )

    conn.close()


# ── Main ─────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Load GeoPackage priority layers into PostGIS",
    )
    parser.add_argument("gpkg_path", help="Path to USA.gpkg file")
    parser.add_argument(
        "--layer",
        choices=["lines", "subs", "plants", "all"],
        default="all",
        help="Which layer(s) to load (default: all)",
    )
    parser.add_argument(
        "--clear",
        action="store_true",
        help="Clear existing data before loading",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Count features without loading",
    )
    args = parser.parse_args()

    gpkg_path = args.gpkg_path
    if not Path(gpkg_path).exists():
        log.error("GeoPackage file not found: %s", gpkg_path)
        sys.exit(1)

    if args.dry_run:
        dry_run(gpkg_path)
        return

    session = SessionLocal()
    t0 = time.time()
    total_loaded = 0

    try:
        if args.layer in ("lines", "all"):
            total_loaded += load_power_lines(gpkg_path, session, args.clear)

        if args.layer in ("subs", "all"):
            total_loaded += load_substations(gpkg_path, session, args.clear)

        if args.layer in ("plants", "all"):
            total_loaded += load_power_plants(gpkg_path, session, args.clear)

        elapsed = time.time() - t0
        log.info(
            "All done: %d total records loaded in %.1fs",
            total_loaded, elapsed,
        )
    except Exception:
        session.rollback()
        log.exception("Ingestion failed")
        sys.exit(1)
    finally:
        session.close()


if __name__ == "__main__":
    main()
