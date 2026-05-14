"""NYISO MIS public CSV client.

Public, no-key API. The NYISO "Market Information System" (MIS) exposes
daily CSV drops under http://mis.nyiso.com/public/csv/ with two feeds
that matter for day-ahead LMP:

  damlbmp/YYYYMMDDdamlbmp_zone.csv   15 zones, 24 rows each (360 total)
  damlbmp/YYYYMMDDdamlbmp_gen.csv    ~700 generator pnodes, 24 rows each

Monthly archives (useful for backfills) live at:

  damlbmp/YYYYMM01damlbmp_zone_csv.zip
  damlbmp/YYYYMM01damlbmp_gen_csv.zip

The CSV schema is identical across zone and gen:

  Time Stamp, Name, PTID,
  LBMP ($/MWHr),
  Marginal Cost Losses ($/MWHr),
  Marginal Cost Congestion ($/MWHr)

Energy is derived: energy = LBMP - losses - congestion.

Time Stamp is EPT, hour-BEGINNING (00:00..23:00). DST days will have
23 or 25 rows per location depending on spring-forward or fall-back;
we emit them through as-is and let upstream dedup / gap-fill.
"""
from __future__ import annotations

import logging
from datetime import date
from io import BytesIO
from typing import Optional
from zipfile import BadZipFile, ZipFile

import pandas as pd
import requests

logger = logging.getLogger(__name__)

BASE_URL = "http://mis.nyiso.com/public/csv"
DEFAULT_TIMEOUT = 30
DEFAULT_USER_AGENT = "grid-constraint-classifier/1.0 NYISO-MIS-client"

FEED_ZONE = "zone"
FEED_GEN = "gen"
VALID_FEEDS = (FEED_ZONE, FEED_GEN)


class NYISOClient:
    """Thin client for NYISO MIS public CSV drops."""

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
    def _daily_url(operating_date: date, feed: str) -> str:
        if feed not in VALID_FEEDS:
            raise ValueError(f"feed must be one of {VALID_FEEDS}, got {feed!r}")
        stamp = operating_date.strftime("%Y%m%d")
        return f"{BASE_URL}/damlbmp/{stamp}damlbmp_{feed}.csv"

    @staticmethod
    def _monthly_zip_url(year: int, month: int, feed: str) -> str:
        if feed not in VALID_FEEDS:
            raise ValueError(f"feed must be one of {VALID_FEEDS}, got {feed!r}")
        stamp = f"{year:04d}{month:02d}01"
        return f"{BASE_URL}/damlbmp/{stamp}damlbmp_{feed}_csv.zip"

    def fetch_da_lbmp_day(
        self,
        operating_date: date,
        *,
        feed: str = FEED_ZONE,
    ) -> pd.DataFrame:
        """Fetch one day of DA LBMP. Returns the raw CSV as a DataFrame.

        Columns: Time Stamp, Name, PTID, LBMP ($/MWHr),
        Marginal Cost Losses ($/MWHr), Marginal Cost Congestion ($/MWHr).
        """
        url = self._daily_url(operating_date, feed)
        blob = self._get(url)
        return pd.read_csv(BytesIO(blob))

    def fetch_da_lbmp_month(
        self,
        year: int,
        month: int,
        *,
        feed: str = FEED_ZONE,
    ) -> pd.DataFrame:
        """Fetch a full month of DA LBMP via the monthly zip archive.

        The zip contains one CSV per day; we concatenate them into a single
        DataFrame preserving the per-day column set.
        """
        url = self._monthly_zip_url(year, month, feed)
        blob = self._get(url)
        try:
            zf = ZipFile(BytesIO(blob))
        except BadZipFile:
            logger.warning(
                "NYISO monthly zip was not a zip (%d bytes) for %04d-%02d %s",
                len(blob), year, month, feed,
            )
            return pd.DataFrame()

        frames = []
        with zf as z:
            for name in z.namelist():
                if not name.lower().endswith(".csv"):
                    continue
                with z.open(name) as fh:
                    frames.append(pd.read_csv(fh))
        if not frames:
            return pd.DataFrame()
        return pd.concat(frames, ignore_index=True)

    def list_zone_ptids(
        self,
        operating_date: Optional[date] = None,
    ) -> pd.DataFrame:
        """Return the 15 NYISO zone/proxy entries with PTIDs.

        Uses a single daily zonal CSV to build the catalog, since NYISO
        does not publish a standalone catalog feed. Caller picks the
        operating_date; defaults to yesterday to avoid touching today's
        possibly-incomplete file.
        """
        from datetime import date as _date, timedelta
        if operating_date is None:
            operating_date = _date.today() - timedelta(days=1)
        df = self.fetch_da_lbmp_day(operating_date, feed=FEED_ZONE)
        if df.empty or "Name" not in df.columns:
            return pd.DataFrame(columns=["Name", "PTID"])
        cat = (
            df[["Name", "PTID"]]
            .drop_duplicates()
            .sort_values("Name")
            .reset_index(drop=True)
        )
        return cat
