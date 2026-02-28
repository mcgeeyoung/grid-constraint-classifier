"""Interconnection Queue Ingestion CLI.

Ingests interconnection queue data from the LBNL Queues dataset,
which aggregates queue data from all major US ISOs/RTOs.

The LBNL dataset covers ~2,600 GW of proposed generation across
CAISO, ERCOT, ISO-NE, MISO, NYISO, PJM, and SPP.

Data source: https://emp.lbl.gov/queues/
Format: Excel (.xlsx)

Usage:
  python -m cli.ingest_interconnection_queues --file data/lbnl_queues.xlsx
  python -m cli.ingest_interconnection_queues --file data/lbnl_queues.xlsx --dry-run
  python -m cli.ingest_interconnection_queues --file data/lbnl_queues.xlsx --iso CAISO
"""

import argparse
import logging
import sys
from pathlib import Path
from typing import Optional

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def normalize_generation_type(raw: Optional[str]) -> Optional[str]:
    """Map LBNL generation type strings to canonical types."""
    if not raw or pd.isna(raw):
        return None
    raw = str(raw).strip().lower()

    type_map = {
        "solar": "solar",
        "photovoltaic": "solar",
        "pv": "solar",
        "wind": "wind",
        "onshore wind": "wind",
        "offshore wind": "offshore_wind",
        "storage": "storage",
        "battery": "storage",
        "bess": "storage",
        "solar + storage": "solar_storage",
        "solar+storage": "solar_storage",
        "hybrid": "hybrid",
        "natural gas": "gas",
        "gas": "gas",
        "nuclear": "nuclear",
        "hydro": "hydro",
        "pumped storage": "pumped_storage",
        "geothermal": "geothermal",
        "biomass": "biomass",
        "coal": "coal",
        "other": "other",
    }

    for key, val in type_map.items():
        if key in raw:
            return val
    return raw[:50]


def normalize_status(raw: Optional[str]) -> Optional[str]:
    """Map LBNL status strings to canonical statuses."""
    if not raw or pd.isna(raw):
        return None
    raw = str(raw).strip().lower()

    status_map = {
        "active": "active",
        "operational": "completed",
        "completed": "completed",
        "withdrawn": "withdrawn",
        "suspended": "suspended",
        "deactivated": "withdrawn",
    }

    for key, val in status_map.items():
        if key in raw:
            return val
    return raw[:50]


def parse_lbnl_queues(file_path: Path, iso_filter: Optional[str] = None) -> pd.DataFrame:
    """Parse the LBNL Queues Excel file into a normalized DataFrame.

    The LBNL file has columns like:
      Queue ID, Project Name, Entity (ISO/RTO), State, County,
      Capacity (MW), Type (generation type), Status, Queue Date,
      Proposed Completion Date, Withdrawn Date, Point of Interconnection,
      Voltage (kV), etc.
    """
    logger.info(f"Reading {file_path}...")

    # Try reading with different sheet names (LBNL varies)
    try:
        df = pd.read_excel(file_path, sheet_name=0)
    except Exception as e:
        logger.error(f"Failed to read Excel file: {e}")
        raise

    logger.info(f"Read {len(df)} rows with {len(df.columns)} columns")
    logger.info(f"Columns: {list(df.columns)}")

    # Normalize column names - LBNL uses various naming patterns
    col_map = _build_column_map(df.columns)
    df = df.rename(columns=col_map)

    # Filter by ISO if requested
    if iso_filter and "iso" in df.columns:
        iso_upper = iso_filter.upper()
        df = df[df["iso"].str.upper().str.contains(iso_upper, na=False)]
        logger.info(f"Filtered to {len(df)} rows for ISO={iso_upper}")

    # Normalize types and statuses
    if "generation_type" in df.columns:
        df["generation_type"] = df["generation_type"].apply(normalize_generation_type)
    if "queue_status" in df.columns:
        df["queue_status"] = df["queue_status"].apply(normalize_status)

    # Convert capacity to float
    for col in ("capacity_mw", "capacity_mw_storage", "voltage_kv"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Convert dates
    for col in ("date_entered", "date_completed", "date_withdrawn", "proposed_online_date"):
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce").dt.date

    return df


def _build_column_map(columns) -> dict:
    """Map LBNL column names to our canonical names."""
    col_map = {}
    for col in columns:
        cl = col.strip().lower().replace(" ", "_")

        if cl in ("queue_id", "request_id", "project_id", "ia_queue_id"):
            col_map[col] = "queue_id"
        elif cl in ("project_name", "project", "name"):
            col_map[col] = "project_name"
        elif cl in ("entity", "region", "iso", "rto", "iso/rto"):
            col_map[col] = "iso"
        elif cl == "state" or cl == "st":
            col_map[col] = "state"
        elif cl == "county":
            col_map[col] = "county"
        elif cl in ("capacity_(mw)", "capacity_mw", "nameplate_capacity_(mw)", "mw"):
            col_map[col] = "capacity_mw"
        elif "storage" in cl and "mw" in cl:
            col_map[col] = "capacity_mw_storage"
        elif cl in ("type", "generation_type", "fuel_type", "technology"):
            col_map[col] = "generation_type"
        elif cl in ("status", "queue_status"):
            col_map[col] = "queue_status"
        elif cl in ("queue_date", "date_entered", "received_date", "request_date"):
            col_map[col] = "date_entered"
        elif cl in ("proposed_completion", "proposed_online", "proposed_cod", "cod"):
            col_map[col] = "proposed_online_date"
        elif "withdrawn" in cl and "date" in cl:
            col_map[col] = "date_withdrawn"
        elif cl in ("completed_date", "date_completed", "operational_date"):
            col_map[col] = "date_completed"
        elif cl in ("poi", "point_of_interconnection", "interconnection_point"):
            col_map[col] = "point_of_interconnection"
        elif cl in ("voltage_(kv)", "voltage_kv", "kv"):
            col_map[col] = "voltage_kv"
        elif cl in ("substation", "substation_name"):
            col_map[col] = "substation_name"
        elif cl in ("latitude", "lat"):
            col_map[col] = "latitude"
        elif cl in ("longitude", "lon", "long"):
            col_map[col] = "longitude"

    return col_map


ISO_CODE_MAP = {
    "caiso": "caiso",
    "california": "caiso",
    "ercot": "ercot",
    "texas": "ercot",
    "iso-ne": "isone",
    "isone": "isone",
    "iso ne": "isone",
    "new england": "isone",
    "miso": "miso",
    "nyiso": "nyiso",
    "new york": "nyiso",
    "pjm": "pjm",
    "spp": "spp",
    "southwest": "spp",
}


def map_iso_code(raw: Optional[str]) -> Optional[str]:
    """Map LBNL ISO name to our ISO code."""
    if not raw or pd.isna(raw):
        return None
    raw_lower = str(raw).strip().lower()
    for key, val in ISO_CODE_MAP.items():
        if key in raw_lower:
            return val
    return None


def main():
    parser = argparse.ArgumentParser(description="Ingest LBNL interconnection queue data")
    parser.add_argument("--file", type=Path, required=True, help="Path to LBNL queues Excel file")
    parser.add_argument("--dry-run", action="store_true", help="Parse only, no DB write")
    parser.add_argument("--iso", help="Filter to a single ISO (e.g. CAISO)")
    args = parser.parse_args()

    if not args.file.exists():
        logger.error(f"File not found: {args.file}")
        sys.exit(1)

    df = parse_lbnl_queues(args.file, iso_filter=args.iso)

    if df.empty:
        logger.warning("No data parsed")
        return

    if args.dry_run:
        _print_summary(df)
        return

    _write_to_db(df, str(args.file))


def _print_summary(df: pd.DataFrame):
    """Print summary for dry-run mode."""
    print(f"\n=== LBNL Interconnection Queue: {len(df)} entries ===\n")

    if "iso" in df.columns:
        print("By ISO/RTO:")
        for iso, count in df["iso"].value_counts().items():
            mw = df[df["iso"] == iso]["capacity_mw"].sum() if "capacity_mw" in df.columns else 0
            print(f"  {iso}: {count:,} projects, {mw:,.0f} MW")

    if "generation_type" in df.columns:
        print(f"\nBy generation type:")
        for gtype, count in df["generation_type"].value_counts().head(10).items():
            mw = df[df["generation_type"] == gtype]["capacity_mw"].sum() if "capacity_mw" in df.columns else 0
            print(f"  {gtype}: {count:,} projects, {mw:,.0f} MW")

    if "queue_status" in df.columns:
        print(f"\nBy status:")
        for status, count in df["queue_status"].value_counts().items():
            print(f"  {status}: {count:,}")

    if "state" in df.columns:
        top_states = df["state"].value_counts().head(10)
        print(f"\nTop 10 states:")
        for state, count in top_states.items():
            print(f"  {state}: {count:,}")

    if "capacity_mw" in df.columns:
        total = df["capacity_mw"].sum()
        print(f"\nTotal capacity: {total:,.0f} MW ({total/1000:,.1f} GW)")

    if "date_entered" in df.columns:
        valid = df["date_entered"].dropna()
        if len(valid) > 0:
            print(f"Date range: {valid.min()} to {valid.max()}")

    # Sample
    sample_cols = [c for c in ["queue_id", "iso", "state", "generation_type", "capacity_mw", "queue_status"]
                   if c in df.columns]
    if sample_cols:
        print(f"\nSample (first 10):")
        print(df[sample_cols].head(10).to_string(index=False))

    print()


def _write_to_db(df: pd.DataFrame, source_file: str):
    """Write interconnection queue entries to the database."""
    from app.database import SessionLocal
    from app.models import InterconnectionQueue, ISO

    session = SessionLocal()
    try:
        # Build ISO lookup
        iso_lookup = {iso.iso_code: iso.id for iso in session.query(ISO).all()}
        logger.info(f"Found {len(iso_lookup)} ISOs in DB")

        created = 0
        skipped = 0

        for _, row in df.iterrows():
            queue_id = str(row.get("queue_id", "")).strip()
            if not queue_id:
                skipped += 1
                continue

            # Resolve ISO
            iso_code = map_iso_code(row.get("iso"))
            iso_id = iso_lookup.get(iso_code) if iso_code else None

            entry = InterconnectionQueue(
                queue_id=queue_id,
                iso_id=iso_id,
                project_name=_safe_str(row.get("project_name"), 500),
                state=_safe_str(row.get("state"), 2),
                county=_safe_str(row.get("county"), 100),
                point_of_interconnection=_safe_str(row.get("point_of_interconnection"), 300),
                latitude=_safe_float(row.get("latitude")),
                longitude=_safe_float(row.get("longitude")),
                generation_type=_safe_str(row.get("generation_type"), 50),
                capacity_mw=_safe_float(row.get("capacity_mw")),
                capacity_mw_storage=_safe_float(row.get("capacity_mw_storage")),
                queue_status=_safe_str(row.get("queue_status"), 50),
                date_entered=row.get("date_entered") if pd.notna(row.get("date_entered")) else None,
                date_completed=row.get("date_completed") if pd.notna(row.get("date_completed")) else None,
                date_withdrawn=row.get("date_withdrawn") if pd.notna(row.get("date_withdrawn")) else None,
                proposed_online_date=row.get("proposed_online_date") if pd.notna(row.get("proposed_online_date")) else None,
                voltage_kv=_safe_float(row.get("voltage_kv")),
                substation_name=_safe_str(row.get("substation_name"), 300),
                data_source="lbnl",
                source_url=source_file,
            )
            session.add(entry)
            created += 1

            if created % 1000 == 0:
                session.flush()
                logger.info(f"  {created} records flushed...")

        session.commit()
        logger.info(f"Done: {created} created, {skipped} skipped (no queue_id)")
        print(f"\nQueue ingestion complete: {created} entries written\n")

    except Exception as e:
        session.rollback()
        logger.error(f"Failed: {e}")
        raise
    finally:
        session.close()


def _safe_str(val, max_len: int = 500) -> Optional[str]:
    """Safely convert value to string, truncating if needed."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    s = str(val).strip()
    return s[:max_len] if s else None


def _safe_float(val) -> Optional[float]:
    """Safely convert value to float."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


if __name__ == "__main__":
    main()
