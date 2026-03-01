"""Direct PJM DA LMP fetch with server-side pnode_id filtering.

gridstatus downloads ALL nodes then filters client-side for pre-archive dates,
making it impractical (196 pages x 50K rows per month). This script calls the
PJM Data Miner API directly with pnode_id filtering, getting only the rows we need.

Usage:
    python scripts/pjm_direct_fetch.py
"""

import os
import sys
import time
import logging
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import requests

# Add project root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

PJM_API_KEY = os.environ.get("PJM_API_KEY", "")
PJM_BASE_URL = "https://api.pjm.com/api/v1/da_hrl_lmps"

# Nodes to fetch: SOUTH interface + WESTERN HUB
# node_id values must match ba_interface_map.json and _resolve_lmp_nodes()
NODES = {
    "2156111904": "2156111904",            # SOUTH interface - stored as pnode_id
    "51288": "PJM_WESTERN_BASELINE",       # WESTERN HUB baseline
}

RATE_LIMIT_SEC = 6.0  # PJM rate limits aggressively


def fetch_pjm_lmp(pnode_id: str, start_date: date, end_date: date) -> pd.DataFrame:
    """Fetch DA LMP for a specific pnode_id from PJM API with server-side filtering."""
    headers = {"Ocp-Apim-Subscription-Key": PJM_API_KEY}
    all_rows = []

    # Chunk by month to keep response sizes manageable
    chunk_start = start_date
    while chunk_start < end_date:
        chunk_end = min(chunk_start + timedelta(days=30), end_date)
        start_str = chunk_start.strftime("%m/%d/%Y 00:00")
        end_str = chunk_end.strftime("%m/%d/%Y 00:00")

        logger.info(f"  Fetching pnode {pnode_id}: {chunk_start} to {chunk_end}")

        start_row = 1
        while True:
            params = {
                "pnode_id": pnode_id,
                "datetime_beginning_ept": f"{start_str}to{end_str}",
                "row_is_current": "TRUE",
                "startRow": start_row,
                "rowCount": 5000,
            }

            for attempt in range(5):
                try:
                    time.sleep(RATE_LIMIT_SEC)
                    resp = requests.get(PJM_BASE_URL, params=params, headers=headers, timeout=60)
                    if resp.status_code == 429:
                        wait = 2 ** (attempt + 2)
                        logger.warning(f"  Rate limited (429). Waiting {wait}s...")
                        time.sleep(wait)
                        continue
                    resp.raise_for_status()
                    break
                except requests.RequestException as e:
                    if attempt < 4:
                        wait = 2 ** (attempt + 1)
                        logger.warning(f"  Retry {attempt+1}: {e}. Waiting {wait}s...")
                        time.sleep(wait)
                    else:
                        logger.error(f"  Failed after 5 attempts: {e}")
                        return pd.DataFrame()

            data = resp.json()
            items = data.get("items", [])
            if not items:
                break

            all_rows.extend(items)
            logger.info(f"    Got {len(items)} rows (total: {len(all_rows)})")

            total_count = data.get("totalCount", 0)
            start_row += len(items)
            if start_row > total_count:
                break

        chunk_start = chunk_end

    if not all_rows:
        return pd.DataFrame()

    df = pd.DataFrame(all_rows)
    return df


def normalize_pjm(df: pd.DataFrame, node_id: str) -> pd.DataFrame:
    """Normalize PJM API response to canonical LMP schema."""
    if df.empty:
        return pd.DataFrame()

    out = pd.DataFrame()

    # PJM uses datetime_beginning_utc or datetime_beginning_ept
    if "datetime_beginning_utc" in df.columns:
        ts = pd.to_datetime(df["datetime_beginning_utc"])
        if ts.dt.tz is not None:
            ts = ts.dt.tz_convert("UTC").dt.tz_localize(None)
    elif "datetime_beginning_ept" in df.columns:
        ts = pd.to_datetime(df["datetime_beginning_ept"])
        # EPT is US/Eastern, convert to UTC
        ts = ts.dt.tz_localize("US/Eastern", ambiguous="NaT", nonexistent="NaT")
        ts = ts.dt.tz_convert("UTC").dt.tz_localize(None)
    else:
        logger.error(f"No timestamp column found in PJM data: {df.columns.tolist()}")
        return pd.DataFrame()

    out["timestamp_utc"] = ts
    out["node_id"] = node_id

    # PJM Data Miner column names
    out["lmp"] = df["total_lmp_da"].astype(float)
    out["energy_component"] = df["system_energy_price_da"].astype(float)
    out["congestion_component"] = df["congestion_price_da"].astype(float)
    out["loss_component"] = df["marginal_loss_price_da"].astype(float)

    # Drop NaT timestamps and deduplicate
    out = out.dropna(subset=["timestamp_utc"])
    out = out.drop_duplicates(subset=["timestamp_utc", "node_id"], keep="first")
    out = out.sort_values("timestamp_utc").reset_index(drop=True)

    return out


def upsert_lmp_rows(db, rto: str, df) -> int:
    """Insert LMP rows, skipping duplicates."""
    from app.models.congestion import InterfaceLMP

    inserted = 0
    for _, row in df.iterrows():
        ts = row["timestamp_utc"]
        if hasattr(ts, "to_pydatetime"):
            ts = ts.to_pydatetime()
        ts = ts.replace(tzinfo=None)

        existing = (
            db.query(InterfaceLMP.id)
            .filter_by(rto=rto, node_id=row["node_id"], timestamp_utc=ts)
            .first()
        )
        if existing:
            continue

        record = InterfaceLMP(
            rto=rto,
            node_id=row["node_id"],
            timestamp_utc=ts,
            lmp=row.get("lmp"),
            energy_component=row.get("energy_component"),
            congestion_component=row.get("congestion_component"),
            loss_component=row.get("loss_component"),
            market_type="DA",
        )
        db.add(record)
        inserted += 1

        if inserted % 1000 == 0:
            db.commit()

    db.commit()
    return inserted


def main():
    if not PJM_API_KEY:
        logger.error("PJM_API_KEY not set in .env")
        sys.exit(1)

    from app.database import SessionLocal
    from app.models.congestion import InterfaceLMP

    db = SessionLocal()
    # PJM archive boundary: pnode_id filter only works for non-archived data
    # (~March 2024+). Jan-Feb 2024 archived data doesn't support server-side
    # pnode_id filtering, so we start from March.
    start_date = date(2024, 3, 1)
    end_date = date(2025, 1, 1)

    try:
        for pnode_id, node_label in NODES.items():
            logger.info(f"=== {node_label} (pnode_id={pnode_id}) ===")
            raw_df = fetch_pjm_lmp(pnode_id, start_date, end_date)

            if raw_df.empty:
                logger.warning(f"No data for {node_label}")
                continue

            logger.info(f"Raw rows: {len(raw_df)}")
            df = normalize_pjm(raw_df, node_label)
            logger.info(f"Normalized rows: {len(df)}")

            inserted = upsert_lmp_rows(db, "PJM", df)
            logger.info(f"{node_label}: {inserted} rows inserted")

        total = db.query(InterfaceLMP).filter_by(rto="PJM").count()
        logger.info(f"Total PJM LMP rows in DB: {total}")

    except Exception as e:
        db.rollback()
        logger.error(f"PJM ingestion failed: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
