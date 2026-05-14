"""ISO-NE public DA LMP CSV client.

Public, no-key archive at:

  https://www.iso-ne.com/static-transform/csv/histRpts/da-lmp/WW_DALMP_ISO_YYYYMMDD.csv

The page that links these (https://www.iso-ne.com/isoexpress/web/reports/pricing/-/tree/lmps-da-hourly)
has a CAPTCHA on the interactive download button, but the underlying CSV
URL serves directly with a User-Agent header. ISO-NE retains seven years
of daily files. No equivalent monthly zip; backfill loops by day.

Daily file layout (one CSV per operating date):

  4 prose rows starting with "C"   - title, filename, report-for, generated-at
  2 header rows starting with "H"  - column names, then column data types
  N data rows starting with "D"    - ~30k rows = ~1.2k locations x 24 hour-ending slots

Columns we care about:

  Date, Hour Ending, Location ID, Location Name, Location Type,
  Locational Marginal Price, Energy Component, Congestion Component,
  Marginal Loss Component

`Location Type` is one of: HUB, HUB NODE, LOAD ZONE, NETWORK NODE,
EXT. NODE, DRRAZ. The eight ISO-NE load zones live under LOAD ZONE
with PTIDs 4001-4008 and names like `.Z.MAINE`, `.Z.NEMASSBOST`.

`Hour Ending` is `01..24` in **hour-ending EPT** (no DST quirks
beyond the standard 23/25-hour transition days).
"""
from __future__ import annotations

import logging
from datetime import date
from io import StringIO

import pandas as pd
import requests

logger = logging.getLogger(__name__)

BASE_URL = "https://www.iso-ne.com/static-transform/csv/histRpts/da-lmp"

# Some ISO-NE static-content paths reject default requests UA; sending a
# browser-like UA succeeds.
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "text/csv,*/*;q=0.8",
}

# Column names we assign after stripping the leading record-type column ("D").
# The on-disk header repeats the data type per column ("Date","HE","String",...).
DA_LMP_COLUMNS = [
    "date",
    "hour_ending",
    "location_id",
    "location_name",
    "location_type",
    "lmp",
    "energy_component",
    "congestion_component",
    "marginal_loss_component",
]


class ISONEClient:
    """HTTP client for the ISO-NE public DA LMP daily archive."""

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

    def _url_for(self, operating_date: date) -> str:
        stamp = operating_date.strftime("%Y%m%d")
        return f"{self.base_url}/WW_DALMP_ISO_{stamp}.csv"

    def fetch_da_lmp_day(self, operating_date: date) -> pd.DataFrame:
        """Fetch one operating-day file and return data rows as a DataFrame.

        The "C" comment block and the two "H" header rows are stripped; the
        returned frame has the columns listed in `DA_LMP_COLUMNS` with prices
        as floats and `location_id` as a string. Empty frame on 404 / parse
        failure (logged).
        """
        url = self._url_for(operating_date)
        logger.info("ISO-NE DA LMP fetch: %s", url)
        resp = self.session.get(url, timeout=self.timeout_s)
        if resp.status_code == 404:
            logger.warning("ISO-NE DA LMP 404: %s", url)
            return pd.DataFrame(columns=DA_LMP_COLUMNS)
        resp.raise_for_status()

        return _parse_da_lmp_csv(resp.text)


def _parse_da_lmp_csv(text: str) -> pd.DataFrame:
    """Parse the raw CSV body. Tolerates the C/H/D/T record-type column.

    The file mixes 2-column comment rows (`"C",...`), 10-column header rows
    (`"H",...`), 10-column data rows (`"D",...`), and a trailing `"T"`
    line-count row. pandas's column-count inference picks 2 from the first
    `"C"` row and discards everything wider, so we pre-filter to `"D"` rows
    before parsing.
    """
    data_lines = [ln for ln in text.splitlines() if ln.startswith('"D"')]
    if not data_lines:
        return pd.DataFrame(columns=DA_LMP_COLUMNS)

    raw = pd.read_csv(
        StringIO("\n".join(data_lines)),
        header=None,
        names=["_rectype"] + DA_LMP_COLUMNS,
        dtype=str,
        engine="c",
    )
    if raw.empty:
        return pd.DataFrame(columns=DA_LMP_COLUMNS)
    raw = raw.drop(columns=["_rectype"]).reset_index(drop=True)

    # Cast types. Prices may legitimately be empty for nodes that didn't
    # clear; coerce to NaN.
    for price_col in ("lmp", "energy_component", "congestion_component", "marginal_loss_component"):
        raw[price_col] = pd.to_numeric(raw[price_col], errors="coerce")
    raw["location_id"] = raw["location_id"].astype(str)
    return raw
