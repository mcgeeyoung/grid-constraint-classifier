"""
EIA API v2 client for hourly grid operations data.

Fetches EIA-930 region data (demand, generation, interchange) and
interchange-pair data for balancing authority analysis.

API docs: https://www.eia.gov/opendata/documentation.php
Base URL: https://api.eia.gov/v2/
"""

import logging
import time
from datetime import datetime
from typing import Optional

import pandas as pd
import requests

logger = logging.getLogger(__name__)

BASE_URL = "https://api.eia.gov/v2"


class EIAClient:
    """EIA API v2 client with pagination, rate limiting, and retry."""

    def __init__(
        self,
        api_key: str,
        rate_limit_sec: float = 0.6,
        max_retries: int = 3,
        timeout: int = 60,
    ):
        self.api_key = api_key
        self.rate_limit_sec = rate_limit_sec
        self.max_retries = max_retries
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(
            {"User-Agent": "grid-constraint-classifier/2.0"}
        )

    def fetch_region_data(
        self,
        ba_code: str,
        start: str,
        end: str,
        page_size: int = 5000,
    ) -> pd.DataFrame:
        """Fetch hourly demand, net generation, and total interchange for a BA.

        Args:
            ba_code: EIA balancing authority code (e.g., "BANC").
            start: Start datetime as "YYYY-MM-DDTHH" or "YYYY-MM-DD".
            end: End datetime as "YYYY-MM-DDTHH" or "YYYY-MM-DD".
            page_size: Max rows per API call (EIA max is 5000).

        Returns:
            DataFrame with columns: timestamp_utc, demand_mw, net_generation_mw,
            total_interchange_mw, net_imports_mw. One row per hour.
        """
        endpoint = f"{BASE_URL}/electricity/rto/region-data/data/"
        params = {
            "api_key": self.api_key,
            "frequency": "hourly",
            "data[0]": "value",
            "facets[respondent][]": ba_code,
            "facets[type][]": ["D", "NG", "TI"],
            "start": start,
            "end": end,
            "sort[0][column]": "period",
            "sort[0][direction]": "asc",
            "length": page_size,
        }

        all_rows = self._paginate(endpoint, params, page_size)
        if not all_rows:
            logger.warning(f"No region data returned for {ba_code}")
            return pd.DataFrame()

        df = pd.DataFrame(all_rows)

        # Pivot: each hour has rows for D, NG, TI -> one row per hour
        df["value"] = pd.to_numeric(df["value"], errors="coerce")
        pivot = df.pivot_table(
            index="period",
            columns="type-name",
            values="value",
            aggfunc="first",
        ).reset_index()

        # Normalize column names
        col_map = {
            "period": "timestamp_utc",
            "Demand": "demand_mw",
            "Net generation": "net_generation_mw",
            "Total interchange": "total_interchange_mw",
        }
        pivot = pivot.rename(columns=col_map)

        # Keep only expected columns
        expected = ["timestamp_utc", "demand_mw", "net_generation_mw", "total_interchange_mw"]
        for col in expected:
            if col not in pivot.columns:
                pivot[col] = None
        pivot = pivot[expected]

        # Parse timestamps and compute net imports
        pivot["timestamp_utc"] = pd.to_datetime(pivot["timestamp_utc"], utc=True)
        # EIA convention: positive TI = net exports, negative = net imports
        pivot["net_imports_mw"] = -pivot["total_interchange_mw"]

        return pivot.sort_values("timestamp_utc").reset_index(drop=True)

    def fetch_interchange_pairs(
        self,
        ba_code: str,
        start: str,
        end: str,
        page_size: int = 5000,
    ) -> pd.DataFrame:
        """Fetch hourly interchange between a BA and all its neighbors.

        Returns flows FROM the BA to each neighbor (positive = export).
        To get full picture, also need flows TO the BA.

        Args:
            ba_code: EIA balancing authority code.
            start: Start datetime as "YYYY-MM-DDTHH" or "YYYY-MM-DD".
            end: End datetime as "YYYY-MM-DDTHH" or "YYYY-MM-DD".

        Returns:
            DataFrame with columns: timestamp_utc, from_ba, to_ba, value_mw.
        """
        endpoint = f"{BASE_URL}/electricity/rto/interchange-data/data/"
        params = {
            "api_key": self.api_key,
            "frequency": "hourly",
            "data[0]": "value",
            "facets[fromba][]": ba_code,
            "start": start,
            "end": end,
            "sort[0][column]": "period",
            "sort[0][direction]": "asc",
            "length": page_size,
        }

        all_rows = self._paginate(endpoint, params, page_size)
        if not all_rows:
            return pd.DataFrame()

        df = pd.DataFrame(all_rows)
        df["value"] = pd.to_numeric(df["value"], errors="coerce")

        result = pd.DataFrame({
            "timestamp_utc": pd.to_datetime(df["period"], utc=True),
            "from_ba": df.get("fromba", ba_code),
            "to_ba": df.get("toba", ""),
            "value_mw": df["value"],
        })

        return result.sort_values("timestamp_utc").reset_index(drop=True)

    def _paginate(
        self,
        endpoint: str,
        params: dict,
        page_size: int,
    ) -> list[dict]:
        """Fetch all pages from an EIA endpoint."""
        all_rows: list[dict] = []
        offset = 0

        while True:
            params["offset"] = offset
            data = self._request_with_retry(endpoint, params)
            if data is None:
                break

            response_data = data.get("response", {})
            rows = response_data.get("data", [])
            total = int(response_data.get("total", 0))

            if not rows:
                break

            all_rows.extend(rows)
            logger.debug(
                f"  Fetched {len(all_rows)}/{total} rows (offset {offset})"
            )

            if len(all_rows) >= total:
                break

            offset += page_size
            time.sleep(self.rate_limit_sec)

        return all_rows

    def _request_with_retry(
        self,
        url: str,
        params: dict,
    ) -> Optional[dict]:
        """HTTP GET with exponential backoff retry."""
        for attempt in range(self.max_retries):
            try:
                resp = self.session.get(
                    url, params=params, timeout=self.timeout
                )
                resp.raise_for_status()
                data = resp.json()

                # Check for EIA-specific error responses
                if "error" in data:
                    logger.warning(f"EIA API error: {data['error']}")
                    if attempt < self.max_retries - 1:
                        time.sleep(2 ** attempt)
                        continue
                    return None

                return data

            except requests.exceptions.Timeout:
                logger.warning(
                    f"Timeout (attempt {attempt + 1}/{self.max_retries})"
                )
            except requests.exceptions.RequestException as e:
                logger.warning(
                    f"Request failed (attempt {attempt + 1}/{self.max_retries}): {e}"
                )

            if attempt < self.max_retries - 1:
                time.sleep(2 ** attempt)

        return None
