"""SPP public file-browser client for day-ahead LMPs.

SPP exposes its public market data via a file-browser HTTP API at:

  https://portal.spp.org/file-browser-api/download/{endpoint}?path={path}

where `endpoint` is a feed-specific id (e.g. `da-lmp-by-settlement-location`,
`rtbm-lmp-by-location`) and `path` is the file path inside that feed's
tree. No auth or key. The SPP Markets Public Data Guide and the
gridstatus reference implementation document the full catalog.

For day-ahead hourly LMPs by Settlement Location the path pattern is:

  /{YYYY}/{MM}/By_Day/DA-LMP-SL-{YYYYMMDD}0100.csv

The trailing `0100` is a quirk of the SPP filename convention (it is
not a per-hour file -- the daily file already contains all 24 HE
slots). One day file is ~4 MB / ~38k rows = ~1,580 settlement
locations x 24 HE.

CSV columns:

  Interval, GMTIntervalEnd, BAA, Settlement Location, Pnode,
  LMP, MLC, MCC, MEC

`Interval` is hour-ending in **Central Prevailing Time** (follows DST);
`GMTIntervalEnd` is the same instant in GMT. Components sum exactly to
total LMP (LMP = MEC + MCC + MLC).
"""
from __future__ import annotations

import logging
from datetime import date
from io import StringIO

import pandas as pd
import requests

logger = logging.getLogger(__name__)

BASE_URL = "https://portal.spp.org/file-browser-api/download"
ENDPOINT_DA_LMP_SL = "da-lmp-by-settlement-location"
ENDPOINT_RTBM_LMP_SL = "rtbm-lmp-by-location"

# SPP portal sits behind a WAF that occasionally rejects default
# requests UAs; sending a browser UA is reliable.
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "text/csv,*/*;q=0.8",
}

DA_LMP_COLUMNS = [
    "Interval",
    "GMTIntervalEnd",
    "BAA",
    "Settlement Location",
    "Pnode",
    "LMP",
    "MLC",
    "MCC",
    "MEC",
]


class SPPClient:
    """HTTP client for the SPP public file-browser API."""

    def __init__(
        self,
        base_url: str = BASE_URL,
        timeout_s: int = 60,
        session: requests.Session | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s
        self.session = session or requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)

    def _download(self, endpoint: str, path: str) -> str:
        """GET the raw text body for a file-browser path. Raises on non-200."""
        # `requests` will URL-encode the path query parameter for us.
        url = f"{self.base_url}/{endpoint}"
        params = {"path": path}
        logger.info("SPP fetch: %s path=%s", url, path)
        resp = self.session.get(url, params=params, timeout=self.timeout_s)
        if resp.status_code == 404:
            logger.warning("SPP 404: %s path=%s", url, path)
            return ""
        resp.raise_for_status()
        return resp.text

    def fetch_da_lmp_day(self, operating_date: date) -> pd.DataFrame:
        """Fetch one operating-day SL-level DA LMP CSV.

        Returns a DataFrame with the columns named in `DA_LMP_COLUMNS`,
        prices coerced to float. Empty frame on 404 / parse failure.
        """
        path = (
            f"/{operating_date.strftime('%Y')}"
            f"/{operating_date.strftime('%m')}"
            f"/By_Day/DA-LMP-SL-{operating_date.strftime('%Y%m%d')}0100.csv"
        )
        text = self._download(ENDPOINT_DA_LMP_SL, path)
        if not text:
            return pd.DataFrame(columns=DA_LMP_COLUMNS)

        df = pd.read_csv(StringIO(text), dtype=str)
        if df.empty:
            return pd.DataFrame(columns=DA_LMP_COLUMNS)

        # Reorder / restrict to the documented columns; tolerate extras
        # (BAA was added to the schema mid-2024).
        for col in DA_LMP_COLUMNS:
            if col not in df.columns:
                df[col] = pd.NA
        df = df[DA_LMP_COLUMNS].copy()

        for price_col in ("LMP", "MLC", "MCC", "MEC"):
            df[price_col] = pd.to_numeric(df[price_col], errors="coerce")
        return df

    def fetch_rtbm_lmp_latest(self) -> pd.DataFrame:
        """Convenience pull of the latest 5-minute RTBM SL-level LMP snapshot."""
        text = self._download(ENDPOINT_RTBM_LMP_SL, "/RTBM-LMP-SL-latestInterval.csv")
        if not text:
            return pd.DataFrame()
        return pd.read_csv(StringIO(text))
