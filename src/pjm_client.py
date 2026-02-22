"""
Rate-limited PJM Data Miner 2 API client.

Enforces dual rate limiting:
  - Minimum 10s between consecutive requests
  - Sliding window: max 6 requests per 60s (non-member limit)

Handles 429 responses with exponential backoff (30s, 60s, 120s).
Auto-paginates via response `links` array.
"""

import time
import logging
from collections import deque
from typing import Optional

import requests
import pandas as pd

logger = logging.getLogger(__name__)

BASE_URL = "https://api.pjm.com/api/v1/"
DEFAULT_ROW_COUNT = 50000

# Rate limit settings
MIN_DELAY_S = 10          # Minimum seconds between requests
WINDOW_S = 60             # Sliding window duration
MAX_REQUESTS_PER_WINDOW = 6
BACKOFF_SCHEDULE = [30, 60, 120]  # Seconds to wait on 429


class PJMClient:
    """Rate-limited client for PJM Data Miner 2 API."""

    def __init__(self, subscription_key: str):
        self.subscription_key = subscription_key
        self.session = requests.Session()
        self.session.headers.update({
            "Ocp-Apim-Subscription-Key": subscription_key,
        })
        self._request_times: deque = deque()
        self._last_request_time: float = 0
        self._request_count: int = 0

    def _enforce_rate_limit(self):
        """Wait as needed to satisfy both rate limit constraints."""
        now = time.time()

        # 1) Minimum delay between requests
        elapsed = now - self._last_request_time
        if elapsed < MIN_DELAY_S:
            wait = MIN_DELAY_S - elapsed
            logger.debug(f"Rate limit: waiting {wait:.1f}s (min delay)")
            time.sleep(wait)
            now = time.time()

        # 2) Sliding window: purge old timestamps, check count
        while self._request_times and (now - self._request_times[0]) > WINDOW_S:
            self._request_times.popleft()

        if len(self._request_times) >= MAX_REQUESTS_PER_WINDOW:
            oldest = self._request_times[0]
            wait = WINDOW_S - (now - oldest) + 1  # +1s buffer
            logger.info(f"Rate limit: sliding window full, waiting {wait:.1f}s")
            time.sleep(wait)
            now = time.time()
            # Re-purge after waiting
            while self._request_times and (now - self._request_times[0]) > WINDOW_S:
                self._request_times.popleft()

    def _record_request(self):
        """Record a request timestamp for rate limiting."""
        now = time.time()
        self._request_times.append(now)
        self._last_request_time = now
        self._request_count += 1

    def _make_request(self, url: str, params: Optional[dict] = None) -> dict:
        """Make a single rate-limited request with 429 backoff."""
        self._enforce_rate_limit()

        for attempt, backoff in enumerate(BACKOFF_SCHEDULE):
            self._record_request()
            logger.info(
                f"API request #{self._request_count}: "
                f"GET {url.split('?')[0]} "
                f"(params: {list(params.keys()) if params else 'none'})"
            )

            resp = self.session.get(url, params=params, timeout=60)

            if resp.status_code == 429:
                logger.warning(
                    f"429 rate limited. Backing off {backoff}s "
                    f"(attempt {attempt + 1}/{len(BACKOFF_SCHEDULE)})"
                )
                time.sleep(backoff)
                self._enforce_rate_limit()
                continue

            resp.raise_for_status()
            return resp.json()

        # Final attempt after all backoffs
        self._enforce_rate_limit()
        self._record_request()
        resp = self.session.get(url, params=params, timeout=60)
        resp.raise_for_status()
        return resp.json()

    def _get_next_url(self, response_data: dict) -> Optional[str]:
        """Extract next-page URL from response links."""
        links = response_data.get("links", [])
        for link in links:
            if link.get("rel") == "next":
                return link.get("href")
        return None

    def query(
        self,
        endpoint: str,
        params: Optional[dict] = None,
        max_pages: int = 20,
    ) -> pd.DataFrame:
        """
        Query a PJM API endpoint with auto-pagination.

        Returns all pages concatenated into a single DataFrame.
        """
        if params is None:
            params = {}
        if "rowCount" not in params:
            params["rowCount"] = DEFAULT_ROW_COUNT
        if "startRow" not in params:
            params["startRow"] = 1

        url = f"{BASE_URL}{endpoint}"
        all_items = []
        page = 0

        while url and page < max_pages:
            page += 1
            if page == 1:
                data = self._make_request(url, params=params)
            else:
                # Next-page URL includes all params already
                data = self._make_request(url)

            items = data.get("items", [])
            if not items:
                logger.info(f"Page {page}: no items returned, stopping")
                break

            all_items.extend(items)
            total = data.get("totalRows", "?")
            logger.info(f"Page {page}: got {len(items)} rows (total: {total})")

            url = self._get_next_url(data)

        df = pd.DataFrame(all_items)
        logger.info(f"Query complete: {len(df)} total rows across {page} page(s)")
        return df

    def query_lmps(
        self,
        datetime_beginning_ept: str,
        lmp_type: str = "ZONE",
        zone: Optional[str] = None,
        fields: Optional[str] = None,
        **extra_params,
    ) -> pd.DataFrame:
        """
        Query day-ahead hourly LMPs.

        Args:
            datetime_beginning_ept: Date range, e.g. "1/1/2025 00:00to12/31/2025 23:00"
            lmp_type: "ZONE", "GEN", "LOAD", "AGGREGATE", etc.
            zone: Filter by zone name (e.g. "DOM")
            fields: Comma-separated column names to return
        """
        params = {
            "datetime_beginning_ept": datetime_beginning_ept,
            "type": lmp_type,
            "rowCount": DEFAULT_ROW_COUNT,
            "sort": "datetime_beginning_ept",
            "order": "asc",
        }
        if zone:
            params["zone"] = zone
        if fields:
            params["fields"] = fields
        params.update(extra_params)

        return self.query("da_hrl_lmps", params=params)

    def query_pnodes(
        self,
        pnode_type: Optional[str] = None,
        zone: Optional[str] = None,
        **extra_params,
    ) -> pd.DataFrame:
        """Query pnode definitions."""
        params = {"rowCount": DEFAULT_ROW_COUNT}
        if pnode_type:
            params["type"] = pnode_type
        if zone:
            params["zone"] = zone
        params["row_is_current"] = "TRUE"
        params.update(extra_params)

        return self.query("pnodes", params=params)


def smoke_test(subscription_key: str) -> bool:
    """
    Quick validation: pull 5 rows of zone LMPs for one day.
    Returns True if successful.
    """
    client = PJMClient(subscription_key)
    logger.info("Smoke test: fetching 5 rows of zone LMPs...")

    params = {
        "datetime_beginning_ept": "1/1/2025 00:00to1/1/2025 05:00",
        "type": "ZONE",
        "rowCount": 5,
        "fields": "datetime_beginning_ept,pnode_name,total_lmp_da,congestion_price_da",
    }
    df = client.query("da_hrl_lmps", params=params, max_pages=1)

    if len(df) > 0:
        logger.info(f"Smoke test passed. Got {len(df)} rows.")
        logger.info(f"Columns: {list(df.columns)}")
        logger.info(f"Sample:\n{df.head()}")
        return True
    else:
        logger.error("Smoke test failed: no data returned")
        return False


if __name__ == "__main__":
    import os
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    key = os.environ.get("PJM_SUBSCRIPTION_KEY", "")
    if not key:
        print("Set PJM_SUBSCRIPTION_KEY environment variable")
    else:
        smoke_test(key)
