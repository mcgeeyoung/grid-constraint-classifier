"""MISO market reports public CSV client.

Public, no-key API. MISO drops daily day-ahead LMP files at:

  https://docs.misoenergy.org/marketreports/YYYYMMDD_da_expost_lmp.csv
  https://docs.misoenergy.org/marketreports/YYYYMMDD_da_exante_lmp.csv

Each daily file is wide-format: one row per (Node, Value) triple where
Value is one of {LMP, MCC, MLC}, with 24 hour-ending columns HE 1..HE 24.
Typical row count: ~7,700 (2,500+ nodes * 3 values). File is ~1.2 MB.

Header block (first four rows) is human prose and must be skipped; the
actual header is on the fifth line.

MISO publishes two variants:
  - ExPost:  settled LMP after the market clears (the authoritative price)
  - ExAnte:  LMPs submitted to clear the market (pre-settlement)
For pilot settlement math, use ExPost.
"""
from __future__ import annotations

import logging
from datetime import date
from io import BytesIO
from typing import Literal

import pandas as pd
import requests

logger = logging.getLogger(__name__)

BASE_URL = "https://docs.misoenergy.org/marketreports"
DEFAULT_TIMEOUT = 60
DEFAULT_USER_AGENT = "grid-constraint-classifier/1.0 MISO-marketreports-client"

VARIANT_EXPOST: Literal["expost"] = "expost"
VARIANT_EXANTE: Literal["exante"] = "exante"
VALID_VARIANTS = (VARIANT_EXPOST, VARIANT_EXANTE)

# Header prose on rows 0-3; actual column header on row 4 (0-indexed).
HEADER_ROW_SKIP = 4


class MISOClient:
    """Thin client for MISO market-reports daily LMP drops."""

    def __init__(
        self,
        *,
        timeout: int = DEFAULT_TIMEOUT,
        user_agent: str = DEFAULT_USER_AGENT,
    ):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": user_agent})

    def _get(self, url: str) -> bytes:
        r = self.session.get(url, timeout=self.timeout, allow_redirects=True)
        r.raise_for_status()
        return r.content

    @staticmethod
    def _daily_url(operating_date: date, variant: str) -> str:
        if variant not in VALID_VARIANTS:
            raise ValueError(f"variant must be one of {VALID_VARIANTS}, got {variant!r}")
        stamp = operating_date.strftime("%Y%m%d")
        return f"{BASE_URL}/{stamp}_da_{variant}_lmp.csv"

    def fetch_da_lmp_day(
        self,
        operating_date: date,
        *,
        variant: str = VARIANT_EXPOST,
    ) -> pd.DataFrame:
        """Fetch one day of DA LMP. Returns the parsed wide-format DataFrame.

        Columns after parsing:
          Node, Type, Value, HE 1, HE 2, ..., HE 24
        where Type is one of {Gennode, Hub, Interface, Loadzone} and
        Value is one of {LMP, MCC, MLC}.
        """
        url = self._daily_url(operating_date, variant)
        blob = self._get(url)
        df = pd.read_csv(BytesIO(blob), skiprows=HEADER_ROW_SKIP)
        # Drop any trailing blank rows introduced by the file footer.
        if "Node" in df.columns:
            df = df.loc[df["Node"].notna() & (df["Node"].astype(str) != "")].copy()
        return df.reset_index(drop=True)
