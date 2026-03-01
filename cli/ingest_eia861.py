"""EIA Form 861 Utility Registry Ingestion CLI.

Downloads and parses the EIA-861 dataset to populate the utilities table
with ~3,200 US electric utilities including EIA ID, type, state, and
customer/sales data.

Usage:
  python -m cli.ingest_eia861
  python -m cli.ingest_eia861 --year 2023
  python -m cli.ingest_eia861 --dry-run
  python -m cli.ingest_eia861 --dry-run --state CA
"""

import argparse
import io
import logging
import sys
import zipfile
from pathlib import Path
from typing import Optional

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# EIA-861 data lives at a predictable URL pattern
EIA_861_BASE = "https://www.eia.gov/electricity/data/eia861"
DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "eia861"


def download_eia861(year: int, cache_dir: Path) -> Path:
    """Download EIA-861 ZIP for a given year. Returns path to cached ZIP."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    zip_path = cache_dir / f"f861{year}.zip"

    if zip_path.exists():
        logger.info(f"Using cached {zip_path.name}")
        return zip_path

    # EIA puts the latest year at zip/ and older years at archive/zip/
    urls = [
        f"{EIA_861_BASE}/zip/f861{year}.zip",
        f"{EIA_861_BASE}/archive/zip/f861{year}.zip",
    ]

    for url in urls:
        logger.info(f"Trying {url}...")
        resp = requests.get(url, timeout=120, allow_redirects=False)
        if resp.status_code in (301, 302, 404):
            logger.info(f"  {resp.status_code}, trying next URL")
            continue
        resp.raise_for_status()
        # Verify it's actually a ZIP, not an HTML error page
        if resp.content[:4] != b"PK\x03\x04":
            logger.warning(f"  Response is not a ZIP file, trying next URL")
            continue
        zip_path.write_bytes(resp.content)
        logger.info(f"Downloaded {len(resp.content) / 1024 / 1024:.1f} MB -> {zip_path.name}")
        return zip_path

    raise RuntimeError(f"Could not download EIA-861 for year {year}. Tried: {urls}")


def read_eia_excel(raw_bytes: bytes, marker_col: str = "Utility Number") -> pd.DataFrame:
    """Read an EIA Excel file, auto-detecting the header row.

    EIA-861 files have group-header rows before the actual column names.
    This function tries header rows 0-3 until it finds the one containing
    the expected marker column.
    """
    for header_row in range(4):
        df = pd.read_excel(io.BytesIO(raw_bytes), header=header_row)
        if marker_col in df.columns:
            return df
    # Fallback: use row 0
    return pd.read_excel(io.BytesIO(raw_bytes), header=0)


def find_file_in_zip(zf: zipfile.ZipFile, pattern: str) -> Optional[str]:
    """Find a file in the ZIP matching a case-insensitive pattern."""
    pattern_lower = pattern.lower()
    for name in zf.namelist():
        if pattern_lower in name.lower() and (
            name.lower().endswith(".xlsx") or name.lower().endswith(".xls")
        ):
            return name
    return None


def parse_utility_data(zip_path: Path) -> pd.DataFrame:
    """Parse the Utility_Data file from the EIA-861 ZIP.

    Returns a DataFrame with columns:
      eia_id, utility_name, state, utility_type, ownership_type
    """
    with zipfile.ZipFile(zip_path) as zf:
        # Find the utility data file
        fname = find_file_in_zip(zf, "utility_data")
        if not fname:
            # Try alternate name patterns
            fname = find_file_in_zip(zf, "Utility_Y")
            if not fname:
                available = [n for n in zf.namelist() if n.endswith((".xlsx", ".xls"))]
                raise FileNotFoundError(
                    f"No utility data file found in ZIP. Available: {available}"
                )

        logger.info(f"Parsing {fname}...")
        with zf.open(fname) as f:
            df = read_eia_excel(f.read())

    # Normalize column names (EIA uses various capitalizations)
    col_map = {}
    for col in df.columns:
        col_lower = str(col).strip().lower().replace(" ", "_")
        if "utility_n" in col_lower and ("number" in col_lower or "num" in col_lower):
            col_map[col] = "eia_id"
        elif "utility_name" in col_lower or (col_lower == "utility_name"):
            col_map[col] = "utility_name"
        elif col_lower in ("state", "st"):
            col_map[col] = "state"
        elif "ownership" in col_lower:
            col_map[col] = "ownership_type"
        elif "entity_type" in col_lower:
            col_map[col] = "entity_type"

    df = df.rename(columns=col_map)

    # Ensure we have the required columns
    if "eia_id" not in df.columns:
        # Fallback: first numeric column is likely the utility ID
        for col in df.columns:
            if df[col].dtype in ("int64", "float64"):
                df = df.rename(columns={col: "eia_id"})
                break

    if "utility_name" not in df.columns:
        # Try first string column after eia_id
        for col in df.columns:
            if col != "eia_id" and df[col].dtype == "object":
                df = df.rename(columns={col: "utility_name"})
                break

    required = ["eia_id", "utility_name"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(
            f"Missing required columns: {missing}. "
            f"Available columns: {list(df.columns)}"
        )

    df["eia_id"] = pd.to_numeric(df["eia_id"], errors="coerce").astype("Int64")
    df = df.dropna(subset=["eia_id"])

    logger.info(f"Parsed {len(df)} utility records")
    return df


def parse_sales_data(zip_path: Path) -> pd.DataFrame:
    """Parse the Sales_Ult_Cust file for customer counts and sales."""
    with zipfile.ZipFile(zip_path) as zf:
        fname = find_file_in_zip(zf, "sales_ult_cust")
        if not fname:
            fname = find_file_in_zip(zf, "Sales_")
        if not fname:
            logger.warning("No sales data file found in ZIP, skipping")
            return pd.DataFrame()

        logger.info(f"Parsing {fname}...")
        with zf.open(fname) as f:
            df = read_eia_excel(f.read())

    # Normalize columns
    col_map = {}
    for col in df.columns:
        col_lower = str(col).strip().lower().replace(" ", "_")
        if "utility_n" in col_lower and ("number" in col_lower or "num" in col_lower):
            col_map[col] = "eia_id"
        elif col_lower in ("state", "st"):
            col_map[col] = "state"
        elif "total" in col_lower and "customer" in col_lower:
            col_map[col] = "customers_total"
        elif "total" in col_lower and ("sales" in col_lower or "mwh" in col_lower):
            col_map[col] = "sales_mwh"

    df = df.rename(columns=col_map)
    if "eia_id" not in df.columns:
        return pd.DataFrame()

    df["eia_id"] = pd.to_numeric(df["eia_id"], errors="coerce").astype("Int64")

    # Aggregate by utility (may have multiple rows per state)
    agg_cols = {}
    if "customers_total" in df.columns:
        agg_cols["customers_total"] = "sum"
    if "sales_mwh" in df.columns:
        agg_cols["sales_mwh"] = "sum"

    if agg_cols:
        sales_agg = df.groupby("eia_id").agg(agg_cols).reset_index()
        return sales_agg

    return pd.DataFrame()


def parse_service_territory(zip_path: Path) -> pd.DataFrame:
    """Parse the Service_Territory file for county mappings."""
    with zipfile.ZipFile(zip_path) as zf:
        fname = find_file_in_zip(zf, "service_territory")
        if not fname:
            logger.warning("No service territory file found in ZIP, skipping")
            return pd.DataFrame()

        logger.info(f"Parsing {fname}...")
        with zf.open(fname) as f:
            df = pd.read_excel(io.BytesIO(f.read()))

    col_map = {}
    for col in df.columns:
        col_lower = col.strip().lower().replace(" ", "_")
        if "utility_n" in col_lower and ("number" in col_lower or "num" in col_lower):
            col_map[col] = "eia_id"
        elif col_lower in ("state", "st"):
            col_map[col] = "state"
        elif "county" in col_lower:
            col_map[col] = "county"

    df = df.rename(columns=col_map)
    if "eia_id" not in df.columns:
        return pd.DataFrame()

    df["eia_id"] = pd.to_numeric(df["eia_id"], errors="coerce").astype("Int64")

    if "county" in df.columns and "state" in df.columns:
        # Build county list per utility
        counties = (
            df.groupby("eia_id")
            .apply(lambda g: list(g["state"].astype(str) + ":" + g["county"].astype(str)))
            .reset_index(name="counties")
        )
        return counties

    return pd.DataFrame()


def map_ownership_type(raw: Optional[str]) -> Optional[str]:
    """Map EIA ownership type to canonical utility_type."""
    if not raw or pd.isna(raw):
        return None
    raw = str(raw).strip().lower()
    mapping = {
        "investor-owned": "IOU",
        "investor owned": "IOU",
        "cooperative": "cooperative",
        "municipal": "municipal",
        "political subdivision": "political_subdivision",
        "state": "political_subdivision",
        "federal": "federal",
        "retail power marketer": "retail_power_marketer",
        "behind the meter": "behind_the_meter",
        "community choice aggregator": "CCA",
    }
    for key, val in mapping.items():
        if key in raw:
            return val
    return raw[:30]


def main():
    parser = argparse.ArgumentParser(description="Ingest EIA-861 utility registry")
    parser.add_argument("--year", type=int, default=2023, help="EIA-861 data year (default: 2023)")
    parser.add_argument("--dry-run", action="store_true", help="Parse only, no DB write")
    parser.add_argument("--state", help="Filter to a single state (e.g. CA)")
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR, help="Cache directory")
    args = parser.parse_args()

    # Download and parse
    zip_path = download_eia861(args.year, args.data_dir)

    utilities_df = parse_utility_data(zip_path)
    sales_df = parse_sales_data(zip_path)
    territory_df = parse_service_territory(zip_path)

    # Merge sales data
    if not sales_df.empty:
        utilities_df = utilities_df.merge(sales_df, on="eia_id", how="left")
        logger.info(f"Merged sales data for {sales_df['eia_id'].nunique()} utilities")

    # Merge territory data
    if not territory_df.empty:
        utilities_df = utilities_df.merge(territory_df, on="eia_id", how="left")
        logger.info(f"Merged territory data for {territory_df['eia_id'].nunique()} utilities")

    # Map ownership type
    if "ownership_type" in utilities_df.columns:
        utilities_df["utility_type"] = utilities_df["ownership_type"].apply(map_ownership_type)
    elif "entity_type" in utilities_df.columns:
        utilities_df["utility_type"] = utilities_df["entity_type"].apply(map_ownership_type)

    # Filter by state if requested
    if args.state:
        if "state" in utilities_df.columns:
            utilities_df = utilities_df[utilities_df["state"] == args.state.upper()]
            logger.info(f"Filtered to {len(utilities_df)} utilities in {args.state.upper()}")

    if args.dry_run:
        _print_summary(utilities_df)
        return

    # Write to DB
    _write_to_db(utilities_df)


def _print_summary(df: pd.DataFrame):
    """Print summary statistics for dry-run mode."""
    print(f"\n=== EIA-861 Utility Registry: {len(df)} utilities ===\n")

    if "utility_type" in df.columns:
        print("By type:")
        for utype, count in df["utility_type"].value_counts().items():
            print(f"  {utype}: {count}")

    if "state" in df.columns:
        top_states = df["state"].value_counts().head(10)
        print(f"\nTop 10 states:")
        for state, count in top_states.items():
            print(f"  {state}: {count}")

    if "customers_total" in df.columns:
        non_null = df["customers_total"].notna().sum()
        total = df["customers_total"].sum()
        print(f"\nCustomer data: {non_null}/{len(df)} utilities, {total:,.0f} total customers")

    if "sales_mwh" in df.columns:
        non_null = df["sales_mwh"].notna().sum()
        total = df["sales_mwh"].sum()
        print(f"Sales data: {non_null}/{len(df)} utilities, {total:,.0f} total MWh")

    # Sample rows
    sample_cols = [c for c in ["eia_id", "utility_name", "state", "utility_type", "customers_total"]
                   if c in df.columns]
    if sample_cols:
        print(f"\nSample (first 10):")
        print(df[sample_cols].head(10).to_string(index=False))

    print()


def _write_to_db(df: pd.DataFrame):
    """Write/update utilities in the database."""
    from app.database import SessionLocal
    from app.models import Utility, Regulator

    # Deduplicate by eia_id (e.g. 88888 "Withheld" appears multiple times)
    df = df.drop_duplicates(subset=["eia_id"], keep="first")
    logger.info(f"After dedup: {len(df)} unique utilities")

    session = SessionLocal()
    try:
        # Build regulator lookup by state
        regulators = {r.state: r.id for r in session.query(Regulator).all()}
        logger.info(f"Found {len(regulators)} regulators in DB")

        created = 0
        updated = 0
        skipped = 0

        for _, row in df.iterrows():
            eia_id = int(row["eia_id"])
            name = str(row.get("utility_name", "")).strip()
            if not name:
                skipped += 1
                continue

            # Generate utility_code from EIA ID
            utility_code = f"eia_{eia_id}"
            state = str(row.get("state", "")).strip() if pd.notna(row.get("state")) else None

            # Check if utility already exists (by eia_id or utility_code)
            existing = (
                session.query(Utility)
                .filter(Utility.eia_id == eia_id)
                .first()
            )
            if not existing:
                existing = (
                    session.query(Utility)
                    .filter(Utility.utility_code == utility_code)
                    .first()
                )

            if existing:
                # Update EIA fields without overwriting HC-specific data
                if existing.eia_id is None:
                    existing.eia_id = eia_id
                if existing.utility_type is None and pd.notna(row.get("utility_type")):
                    existing.utility_type = row["utility_type"]
                if existing.state is None and state:
                    existing.state = state
                if existing.regulator_id is None and state and state in regulators:
                    existing.regulator_id = regulators[state]
                if pd.notna(row.get("customers_total")):
                    existing.customers_total = int(row["customers_total"])
                if pd.notna(row.get("sales_mwh")):
                    existing.sales_mwh = float(row["sales_mwh"])
                counties = row.get("counties")
                if counties is not None and not (isinstance(counties, float) and pd.isna(counties)):
                    existing.service_territory_counties = counties
                updated += 1
            else:
                util = Utility(
                    utility_code=utility_code,
                    utility_name=name,
                    eia_id=eia_id,
                    utility_type=row.get("utility_type") if pd.notna(row.get("utility_type")) else None,
                    state=state,
                    states=[state] if state else None,
                    data_source_type="eia_861",
                    regulator_id=regulators.get(state) if state else None,
                    customers_total=int(row["customers_total"]) if pd.notna(row.get("customers_total")) else None,
                    sales_mwh=float(row["sales_mwh"]) if pd.notna(row.get("sales_mwh")) else None,
                    service_territory_counties=row.get("counties") if row.get("counties") is not None and not (isinstance(row.get("counties"), float) and pd.isna(row["counties"])) else None,
                )
                session.add(util)
                created += 1

            # Batch commit every 500 records
            if (created + updated) % 500 == 0:
                session.flush()

        session.commit()
        logger.info(f"Done: {created} created, {updated} updated, {skipped} skipped")
        print(f"\nEIA-861 ingestion complete: {created} new, {updated} updated, {skipped} skipped\n")

    except Exception as e:
        session.rollback()
        logger.error(f"Failed: {e}")
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()
