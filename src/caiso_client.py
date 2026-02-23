"""
CAISO OASIS API client for Sub-LAP day-ahead LMPs.

No authentication required. Pulls CSV data inside a ZIP archive.
Chunks requests by month (~31-day max per OASIS request).
Pivots LMP_TYPE (LMP, MCC, MCL, MCE) into separate columns.

23 Sub-LAPs: 15 PG&E + 6 SCE + 1 SDG&E + 1 VEA.
"""

import io
import logging
import time
import zipfile
from datetime import datetime, timedelta
from typing import Optional

import pandas as pd
import requests

logger = logging.getLogger(__name__)

BASE_URL = "https://oasis.caiso.com/oasisapi/SingleZip"
MAX_DAYS_PER_REQUEST = 14  # Keep chunks small enough for OASIS volume limit
REQUEST_DELAY_S = 5  # Polite delay between requests
MAX_RETRIES = 3
RETRY_BACKOFF_S = 10  # Base backoff for 429/empty responses
MAX_NODES_PER_REQUEST = 10  # OASIS can reject too many nodes

# All 23 CAISO Sub-LAPs
ALL_SUB_LAPS = [
    # PG&E (15)
    "SLAP_PGCC-APND", "SLAP_PGEB-APND", "SLAP_PGF1-APND",
    "SLAP_PGFG-APND", "SLAP_PGHB-APND", "SLAP_PGKN-APND",
    "SLAP_PGLP-APND", "SLAP_PGNB-APND", "SLAP_PGNC-APND",
    "SLAP_PGNP-APND", "SLAP_PGP2-APND", "SLAP_PGSB-APND",
    "SLAP_PGSF-APND", "SLAP_PGSI-APND", "SLAP_PGST-APND",
    # SCE (6)
    "SLAP_SCEC-APND", "SLAP_SCEN-APND", "SLAP_SCEW-APND",
    "SLAP_SCHD-APND", "SLAP_SCLD-APND", "SLAP_SCNW-APND",
    # SDG&E (1)
    "SLAP_SDG1-APND",
    # VEA (1)
    "SLAP_VEA-APND",
]


class CAISOClient:
    """Rate-limited client for CAISO OASIS API (Sub-LAP LMPs)."""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "grid-constraint-classifier/1.0"})
        self._request_count = 0

    def _fetch_zip_csv(self, params: dict) -> pd.DataFrame:
        """
        Fetch a single OASIS request with retry logic.

        OASIS returns a ZIP file containing one CSV. The CSV has columns like:
        NODE, LMP_TYPE, OPR_DT, OPR_HR, INTERVAL_NUM, MW, VALUE, ...

        Retries on 429 (rate limit) and empty ZIP responses.
        """
        self._request_count += 1
        logger.info(
            f"OASIS request #{self._request_count}: "
            f"{params.get('startdatetime', '?')} to {params.get('enddatetime', '?')} "
            f"({params.get('node', 'all nodes')[:60]}...)"
        )

        for attempt in range(MAX_RETRIES):
            try:
                resp = self.session.get(BASE_URL, params=params, timeout=120)
            except requests.RequestException as e:
                logger.warning(f"Request error (attempt {attempt + 1}): {e}")
                if attempt < MAX_RETRIES - 1:
                    wait = RETRY_BACKOFF_S * (attempt + 1)
                    logger.info(f"Retrying in {wait}s...")
                    time.sleep(wait)
                    continue
                raise

            if resp.status_code == 429:
                wait = RETRY_BACKOFF_S * (attempt + 1)
                logger.warning(f"Rate limited (429), waiting {wait}s before retry...")
                time.sleep(wait)
                continue

            resp.raise_for_status()

            # Response is a ZIP file containing one CSV
            try:
                with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
                    csv_names = [n for n in zf.namelist() if n.endswith(".csv")]
                    if not csv_names:
                        if attempt < MAX_RETRIES - 1:
                            wait = RETRY_BACKOFF_S * (attempt + 1)
                            logger.warning(
                                f"ZIP contains no CSV (attempt {attempt + 1}), "
                                f"retrying in {wait}s..."
                            )
                            time.sleep(wait)
                            continue
                        logger.warning("ZIP contains no CSV files after all retries")
                        return pd.DataFrame()
                    with zf.open(csv_names[0]) as f:
                        df = pd.read_csv(f)
            except zipfile.BadZipFile:
                text = resp.content.decode("utf-8", errors="replace")[:500]
                logger.error(f"Bad ZIP response (likely OASIS error): {text}")
                return pd.DataFrame()

            return df

        logger.error("All retries exhausted")
        return pd.DataFrame()

    def _format_oasis_datetime(self, dt: datetime) -> str:
        """Format datetime for OASIS API: YYYYMMDDTHH:MM-0000 (UTC)."""
        return dt.strftime("%Y%m%dT%H:%M-0000")

    def _date_chunks(self, start_date: str, end_date: str):
        """
        Yield (chunk_start, chunk_end) date pairs, each <= MAX_DAYS_PER_REQUEST.

        OASIS requires UTC timestamps with T08:00-0000 as the day boundary
        (midnight Pacific = 08:00 UTC).
        """
        start = datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.strptime(end_date, "%Y-%m-%d")

        chunk_start = start
        while chunk_start <= end:
            chunk_end = min(chunk_start + timedelta(days=MAX_DAYS_PER_REQUEST), end)
            # OASIS day boundary is T08:00 UTC (midnight Pacific)
            yield (
                chunk_start.strftime("%Y%m%dT08:00-0000"),
                (chunk_end + timedelta(days=1)).strftime("%Y%m%dT08:00-0000"),
            )
            chunk_start = chunk_end + timedelta(days=1)

    @staticmethod
    def _node_batches(nodes: list[str], batch_size: int):
        """Yield node lists in batches of batch_size."""
        for i in range(0, len(nodes), batch_size):
            yield nodes[i : i + batch_size]

    def query_lmps(
        self,
        start_date: str,
        end_date: str,
        nodes: Optional[list[str]] = None,
    ) -> pd.DataFrame:
        """
        Query day-ahead LMPs for CAISO Sub-LAPs.

        Args:
            start_date: "YYYY-MM-DD"
            end_date: "YYYY-MM-DD"
            nodes: List of OASIS node names (e.g. ["SLAP_PGCC-APND"]).
                   Defaults to all 23 Sub-LAPs.

        Returns:
            DataFrame with columns: NODE, datetime_beginning_ept,
            total_lmp_da, congestion_price_da, marginal_loss_price_da,
            system_energy_price_da
        """
        if nodes is None:
            nodes = ALL_SUB_LAPS

        frames = []

        for batch in self._node_batches(nodes, MAX_NODES_PER_REQUEST):
            node_str = ",".join(batch)
            logger.info(f"Pulling batch of {len(batch)} nodes: {batch[0]}...{batch[-1]}")

            for chunk_start, chunk_end in self._date_chunks(start_date, end_date):
                params = {
                    "queryname": "PRC_LMP",
                    "market_run_id": "DAM",
                    "version": "12",
                    "resultformat": "6",  # CSV
                    "startdatetime": chunk_start,
                    "enddatetime": chunk_end,
                    "node": node_str,
                }

                df = self._fetch_zip_csv(params)
                if len(df) > 0:
                    frames.append(df)

                time.sleep(REQUEST_DELAY_S)

        if not frames:
            logger.warning("No CAISO LMP data returned across all chunks")
            return pd.DataFrame()

        raw = pd.concat(frames, ignore_index=True)
        logger.info(f"Raw OASIS data: {len(raw)} rows, columns: {list(raw.columns)}")

        return self._normalize(raw)

    def _normalize(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Normalize OASIS CSV output to canonical columns.

        OASIS CSV has one row per (NODE, LMP_TYPE, OPR_DT, OPR_HR).
        LMP_TYPE values: LMP, MCC (congestion), MCL (loss), MCE (energy).
        We pivot LMP_TYPE into separate columns.
        """
        if df.empty:
            return df

        # Standardize column names (OASIS sometimes has varying case)
        df.columns = df.columns.str.strip().str.upper()

        # Build timestamp from OPR_DT and OPR_HR
        if "OPR_DT" in df.columns and "OPR_HR" in df.columns:
            df["OPR_DT"] = pd.to_datetime(df["OPR_DT"])
            df["OPR_HR"] = pd.to_numeric(df["OPR_HR"], errors="coerce")
            # OPR_HR is 1-24 (hour ending), convert to 0-23
            df["datetime_beginning_ept"] = df["OPR_DT"] + pd.to_timedelta(
                df["OPR_HR"] - 1, unit="h"
            )
        else:
            logger.error(f"Missing OPR_DT/OPR_HR columns. Got: {list(df.columns)}")
            return pd.DataFrame()

        # Ensure VALUE is numeric
        value_col = "VALUE" if "VALUE" in df.columns else "MW"
        if value_col not in df.columns:
            logger.error(f"No VALUE or MW column found. Got: {list(df.columns)}")
            return pd.DataFrame()
        df[value_col] = pd.to_numeric(df[value_col], errors="coerce")

        # Pivot LMP_TYPE into separate columns
        lmp_type_col = "LMP_TYPE" if "LMP_TYPE" in df.columns else None
        if lmp_type_col is None:
            logger.error(f"No LMP_TYPE column. Got: {list(df.columns)}")
            return pd.DataFrame()

        pivot = df.pivot_table(
            index=["NODE", "datetime_beginning_ept"],
            columns=lmp_type_col,
            values=value_col,
            aggfunc="first",
        ).reset_index()

        # Map OASIS LMP_TYPE names to canonical column names
        type_map = {
            "LMP": "total_lmp_da",
            "MCC": "congestion_price_da",
            "MCL": "marginal_loss_price_da",
            "MCE": "system_energy_price_da",
        }
        rename = {}
        for oasis_type, canon_col in type_map.items():
            if oasis_type in pivot.columns:
                rename[oasis_type] = canon_col
        pivot = pivot.rename(columns=rename)

        # Rename NODE to pnode_name
        pivot = pivot.rename(columns={"NODE": "pnode_name"})

        # Derive time columns
        pivot["hour"] = pivot["datetime_beginning_ept"].dt.hour
        pivot["month"] = pivot["datetime_beginning_ept"].dt.month
        pivot["day_of_week"] = pivot["datetime_beginning_ept"].dt.dayofweek

        # Ensure all canonical columns exist
        for col in ["total_lmp_da", "congestion_price_da",
                     "marginal_loss_price_da", "system_energy_price_da"]:
            if col not in pivot.columns:
                pivot[col] = 0.0

        logger.info(
            f"Normalized: {len(pivot)} rows, "
            f"{pivot['pnode_name'].nunique()} nodes, "
            f"date range: {pivot['datetime_beginning_ept'].min()} to "
            f"{pivot['datetime_beginning_ept'].max()}"
        )

        return pivot


def smoke_test() -> bool:
    """Quick validation: fetch one day of LMP data for one Sub-LAP."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    client = CAISOClient()
    logger.info("Smoke test: fetching 1 day of CAISO Sub-LAP LMPs...")

    df = client.query_lmps("2025-01-01", "2025-01-01", ["SLAP_PGCC-APND"])

    if len(df) > 0:
        logger.info(f"Smoke test passed. Got {len(df)} rows.")
        logger.info(f"Columns: {list(df.columns)}")
        logger.info(f"Sample:\n{df.head()}")
        return True
    else:
        logger.error("Smoke test failed: no data returned")
        return False


if __name__ == "__main__":
    smoke_test()
