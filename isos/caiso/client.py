"""CAISO OASIS HTTP client.

Public, no-key API. All responses are zips containing CSV (when
resultformat=6) or XML (default). See the interface spec v5.1.2 and
the prior-research notes at ~/claude/outputs/tmp/caiso-oasis-notes.md
for the full queryname catalog and error codes.

Design notes:
  - Single `SingleZip` endpoint is sufficient for our use case (single
    pilot pnodes + catalog lookups).
  - PRC_LMP windows are capped at 31 days by OASIS; we raise if the
    caller asks for more so the caller chunks its own loop rather than
    silently truncating.
  - HTTP redirects to HTTPS; we hit HTTPS directly and leave
    allow_redirects=True just in case.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from io import BytesIO
from typing import Optional
from zipfile import BadZipFile, ZipFile

import pandas as pd
import requests

logger = logging.getLogger(__name__)

BASE_URL = "https://oasis.caiso.com/oasisapi"
DEFAULT_TIMEOUT = 60
DEFAULT_USER_AGENT = "grid-constraint-classifier/1.0 CAISO-OASIS-client"

# OASIS wants GMT timestamps in this exact shape.
OASIS_TIME_FMT = "%Y%m%dT%H:%M-0000"

# Max window for PRC_LMP DAM queries (error 1004 if exceeded).
MAX_PRC_LMP_WINDOW_DAYS = 31

# OASIS doesn't publish QPS limits, but ~1 request per 5-10 s is the
# practical safe rate. We enforce a min inter-request delay and back off
# on 429/5xx with exponential growth.
MIN_REQUEST_INTERVAL_S = 5.0
RETRY_STATUS = {429, 500, 502, 503, 504}
BACKOFF_SCHEDULE_S = (10.0, 30.0, 60.0)


class CAISOClient:
    """Thin client for CAISO OASIS public reports.

    Enforces a min inter-request delay and retries on 429 / 5xx with the
    backoff schedule above. Sufficient for sequential pulls; for very
    aggressive backfills add an outer rate limiter at the caller.
    """

    def __init__(
        self,
        *,
        timeout: int = DEFAULT_TIMEOUT,
        user_agent: str = DEFAULT_USER_AGENT,
        min_request_interval_s: float = MIN_REQUEST_INTERVAL_S,
    ):
        self.timeout = timeout
        self.min_request_interval_s = min_request_interval_s
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": user_agent})
        self._last_request_at: float = 0.0

    def _enforce_min_interval(self) -> None:
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < self.min_request_interval_s:
            wait = self.min_request_interval_s - elapsed
            logger.debug("CAISO rate limit: sleeping %.1fs", wait)
            time.sleep(wait)

    def _get_zip(self, params: dict) -> bytes:
        """GET /SingleZip and return the raw zip bytes. Retries on 429/5xx."""
        url = f"{BASE_URL}/SingleZip"
        last_exc: Exception | None = None
        for attempt, backoff in enumerate((*BACKOFF_SCHEDULE_S, None)):
            self._enforce_min_interval()
            self._last_request_at = time.monotonic()
            r = self.session.get(
                url, params=params, timeout=self.timeout, allow_redirects=True
            )
            if r.status_code in RETRY_STATUS and backoff is not None:
                logger.warning(
                    "OASIS %s on attempt %d; backing off %.0fs",
                    r.status_code, attempt + 1, backoff,
                )
                time.sleep(backoff)
                continue
            try:
                r.raise_for_status()
            except requests.HTTPError as e:
                last_exc = e
                raise
            return r.content
        # Loop exited without returning -> exhausted retries.
        if last_exc is not None:
            raise last_exc
        raise RuntimeError("CAISO _get_zip exhausted retries without HTTP error")

    def _zip_to_df(self, blob: bytes) -> pd.DataFrame:
        """Unzip in memory and concatenate any CSV files into a DataFrame."""
        try:
            zf = ZipFile(BytesIO(blob))
        except BadZipFile:
            # OASIS sometimes returns an XML error payload instead of a zip
            # when a parameter is invalid. Surface that as an empty frame
            # so the caller can see len==0 and inspect params.
            logger.warning("CAISO response was not a zip (%d bytes)", len(blob))
            return pd.DataFrame()

        with zf as z:
            names = z.namelist()
            if not names:
                return pd.DataFrame()
            frames = []
            for name in names:
                # Skip non-CSV sidecar files if any ever appear.
                if not (name.endswith(".csv") or name.endswith(".CSV")):
                    continue
                with z.open(name) as fh:
                    frames.append(pd.read_csv(fh))
            if not frames:
                # Fall back to reading whatever is in the zip.
                for name in names:
                    with z.open(name) as fh:
                        frames.append(pd.read_csv(fh))
            return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

    def fetch_da_lmp(
        self,
        start: datetime,
        end: datetime,
        *,
        node: Optional[str] = None,
        nodes: Optional[list[str]] = None,
    ) -> pd.DataFrame:
        """Fetch DA (DAM) LMP for a single node or list of nodes.

        Window must be <= 31 days (OASIS hard cap for PRC_LMP).
        Returns one row per (node, hour, LMP_TYPE). LMP_TYPE values
        include 'LMP' (total), 'MCC' (congestion), 'MCL' (loss),
        'MCE' (energy). The price column is named `MW` in the CSV.
        """
        if start.tzinfo is None or end.tzinfo is None:
            raise ValueError("fetch_da_lmp: start and end must be timezone-aware.")

        start_u = start.astimezone(timezone.utc)
        end_u = end.astimezone(timezone.utc)
        if end_u <= start_u:
            raise ValueError("fetch_da_lmp: end must be after start.")
        if (end_u - start_u) > timedelta(days=MAX_PRC_LMP_WINDOW_DAYS):
            raise ValueError(
                f"fetch_da_lmp: window cannot exceed {MAX_PRC_LMP_WINDOW_DAYS} "
                "days; chunk the caller."
            )

        params: dict = {
            "queryname": "PRC_LMP",
            "startdatetime": start_u.strftime(OASIS_TIME_FMT),
            "enddatetime": end_u.strftime(OASIS_TIME_FMT),
            "market_run_id": "DAM",
            "version": "1",
            "resultformat": "6",
        }
        if node:
            params["node"] = node
        elif nodes:
            if len(nodes) > 10:
                raise ValueError(
                    "fetch_da_lmp: OASIS caps node= at 10 values; batch the caller."
                )
            params["node"] = ",".join(nodes)
        else:
            raise ValueError("fetch_da_lmp: pass node= or nodes=.")

        return self._zip_to_df(self._get_zip(params))

    def list_apnodes(self) -> pd.DataFrame:
        """Pull the ATL_APNODE catalog (DLAPs, SLAPs, trading hubs)."""
        now = datetime.now(timezone.utc)
        params = {
            "queryname": "ATL_APNODE",
            "startdatetime": (now - timedelta(days=1)).strftime(OASIS_TIME_FMT),
            "enddatetime": now.strftime(OASIS_TIME_FMT),
            "APnode_id": "ALL",
            "version": "1",
            "resultformat": "6",
        }
        return self._zip_to_df(self._get_zip(params))

    def list_pnodes(self, pnode_type: str = "ALL") -> pd.DataFrame:
        """Pull the ATL_PNODE catalog (bus-level pricing nodes)."""
        now = datetime.now(timezone.utc)
        params = {
            "queryname": "ATL_PNODE",
            "startdatetime": (now - timedelta(days=1)).strftime(OASIS_TIME_FMT),
            "enddatetime": now.strftime(OASIS_TIME_FMT),
            "Pnode_type": pnode_type,
            "version": "1",
            "resultformat": "6",
        }
        return self._zip_to_df(self._get_zip(params))
