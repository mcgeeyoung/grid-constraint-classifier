"""
MISO market report client for day-ahead ex-post LMP data.

Downloads daily CSV files from MISO's public market reports site.
No authentication required. Rate-limited to respect 100 req/min.

Each daily CSV contains all nodes (loadzones, hubs, gennodes, interfaces)
with 24 hourly LMP values in wide format.
"""

import logging
import time
from datetime import datetime, timedelta
from typing import Optional

import pandas as pd
import requests

logger = logging.getLogger(__name__)

BASE_URL = "https://docs.misoenergy.org/marketreports"
REQUEST_DELAY_S = 0.7  # ~85 req/min, under the 100/min limit


class MISOClient:
    """Client for MISO daily DA ex-post LMP CSV reports."""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "grid-constraint-classifier/1.0"})
        self._request_count = 0
        self._failed_dates: list[str] = []

    def _fetch_day(self, date: datetime) -> pd.DataFrame:
        """
        Fetch a single day's DA ex-post LMP CSV.

        URL: https://docs.misoenergy.org/marketreports/YYYYMMDD_da_expost_lmp.csv

        The CSV has columns: Node, Type, Value, HE 1, HE 2, ..., HE 24
        - Type: Loadzone, Hub, Gennode, Interface
        - Value: LMP, MLC (loss), MCC (congestion)
        """
        date_str = date.strftime("%Y%m%d")
        url = f"{BASE_URL}/{date_str}_da_expost_lmp.csv"

        self._request_count += 1
        if self._request_count % 50 == 0:
            logger.info(f"MISO request #{self._request_count}: {date_str}")

        try:
            resp = self.session.get(url, timeout=30)
            resp.raise_for_status()
        except requests.HTTPError as e:
            if resp.status_code == 404:
                # Missing day (holiday, weekend with no data, etc.)
                logger.debug(f"No data for {date_str} (404)")
                self._failed_dates.append(date_str)
                return pd.DataFrame()
            logger.warning(f"HTTP error for {date_str}: {e}")
            self._failed_dates.append(date_str)
            return pd.DataFrame()
        except requests.RequestException as e:
            logger.warning(f"Request failed for {date_str}: {e}")
            self._failed_dates.append(date_str)
            return pd.DataFrame()

        try:
            from io import StringIO
            # MISO CSVs have 4 header lines (title, date, blank, timezone note)
            # before the actual column headers on line 4
            df = pd.read_csv(StringIO(resp.text), skiprows=4)
        except Exception as e:
            logger.warning(f"CSV parse failed for {date_str}: {e}")
            self._failed_dates.append(date_str)
            return pd.DataFrame()

        # Tag with date for later melting
        df["_date"] = date
        return df

    def _melt_wide_to_long(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Convert wide format (HE 1..HE 24 columns) to long format.

        Input columns: Node, Type, Value, HE 1, ..., HE 24, _date
        Output columns: Node, Type, Value, hour, price, datetime_beginning_ept
        """
        # Identify HE columns
        he_cols = [c for c in df.columns if c.startswith("HE ")]
        if not he_cols:
            # Try alternate column naming
            he_cols = [c for c in df.columns if c.startswith("HE")]
            if not he_cols:
                logger.warning(f"No HE columns found. Got: {list(df.columns)}")
                return pd.DataFrame()

        id_cols = [c for c in ["Node", "Type", "Value", "_date"]
                   if c in df.columns]

        melted = df.melt(
            id_vars=id_cols,
            value_vars=he_cols,
            var_name="he_col",
            value_name="price",
        )

        # Extract hour ending number from column name (e.g., "HE 1" -> 1)
        melted["he"] = melted["he_col"].str.extract(r"(\d+)").astype(int)
        # Convert hour ending (1-24) to hour beginning (0-23)
        melted["hour"] = melted["he"] - 1

        # Build timestamp
        melted["datetime_beginning_ept"] = (
            melted["_date"] + pd.to_timedelta(melted["hour"], unit="h")
        )

        melted["price"] = pd.to_numeric(melted["price"], errors="coerce")

        return melted.drop(columns=["he_col", "he", "_date"], errors="ignore")

    def query_lmps(
        self,
        start_date: str,
        end_date: str,
        location_type: str = "Loadzone",
    ) -> pd.DataFrame:
        """
        Query day-ahead LMPs for MISO loadzones (or other location types).

        Args:
            start_date: "YYYY-MM-DD"
            end_date: "YYYY-MM-DD"
            location_type: "Loadzone", "Hub", "Gennode", or "Interface"

        Returns:
            DataFrame with columns: pnode_name, datetime_beginning_ept,
            total_lmp_da, congestion_price_da, marginal_loss_price_da,
            system_energy_price_da, hour, month
        """
        start = datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.strptime(end_date, "%Y-%m-%d")

        logger.info(
            f"Pulling MISO {location_type} LMPs from {start_date} to {end_date} "
            f"({(end - start).days + 1} days)"
        )

        frames = []
        current = start
        while current <= end:
            df = self._fetch_day(current)
            if len(df) > 0:
                frames.append(df)
            current += timedelta(days=1)
            time.sleep(REQUEST_DELAY_S)

        if not frames:
            logger.warning("No MISO LMP data returned across all days")
            return pd.DataFrame()

        raw = pd.concat(frames, ignore_index=True)
        logger.info(f"Raw MISO data: {len(raw)} rows across {len(frames)} days")

        if self._failed_dates:
            logger.info(f"Failed/missing dates: {len(self._failed_dates)}")

        # Filter by location type
        type_col = "Type" if "Type" in raw.columns else None
        if type_col and location_type:
            raw = raw[raw[type_col].str.strip() == location_type]
            logger.info(f"Filtered to {location_type}: {len(raw)} rows")

        if raw.empty:
            return pd.DataFrame()

        # Melt from wide to long format
        long = self._melt_wide_to_long(raw)
        if long.empty:
            return pd.DataFrame()

        return self._normalize(long)

    def _normalize(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Normalize melted MISO data to canonical columns.

        Input has: Node, Value (LMP/MLC/MCC), price, hour, datetime_beginning_ept
        Pivot Value column into separate LMP component columns.
        """
        if df.empty:
            return df

        # Pivot the Value column (LMP, MLC, MCC) into separate price columns
        value_col = "Value" if "Value" in df.columns else None
        if value_col is None:
            logger.error(f"No Value column for pivot. Got: {list(df.columns)}")
            return pd.DataFrame()

        pivot = df.pivot_table(
            index=["Node", "datetime_beginning_ept", "hour"],
            columns=value_col,
            values="price",
            aggfunc="first",
        ).reset_index()

        # Map MISO value names to canonical columns
        value_map = {
            "LMP": "total_lmp_da",
            "MCC": "congestion_price_da",
            "MLC": "marginal_loss_price_da",
        }
        rename = {}
        for miso_name, canon_col in value_map.items():
            if miso_name in pivot.columns:
                rename[miso_name] = canon_col
        pivot = pivot.rename(columns=rename)

        # Derive energy component: LMP - congestion - loss
        if "total_lmp_da" in pivot.columns:
            cong = pivot.get("congestion_price_da", 0)
            loss = pivot.get("marginal_loss_price_da", 0)
            pivot["system_energy_price_da"] = pivot["total_lmp_da"] - cong - loss

        # Rename Node to pnode_name
        pivot = pivot.rename(columns={"Node": "pnode_name"})

        # Derive time columns
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
    """Quick validation: fetch one day of MISO loadzone LMPs."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    client = MISOClient()
    logger.info("Smoke test: fetching 1 day of MISO Loadzone LMPs...")

    df = client.query_lmps("2025-01-01", "2025-01-02")

    if len(df) > 0:
        logger.info(f"Smoke test passed. Got {len(df)} rows.")
        logger.info(f"Columns: {list(df.columns)}")
        logger.info(f"Unique nodes: {df['pnode_name'].nunique()}")
        logger.info(f"Sample:\n{df.head()}")
        return True
    else:
        logger.error("Smoke test failed: no data returned")
        return False


if __name__ == "__main__":
    smoke_test()
