"""
GridStatus-based LMP adapter for congestion pipeline.

Fetches day-ahead LMP data from ISO OASIS/market portals via the gridstatus
library for interface scheduling points and hub baselines.

Supports CAISO, MISO, SPP, and PJM with per-RTO configuration for
chunk sizes, rate limits, hub names, and column normalization.
"""

import logging
import time
from datetime import date, timedelta
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

# Per-RTO configuration
RTO_CONFIG = {
    "CAISO": {
        "gridstatus_class": "CAISO",
        "chunk_days": 30,
        "rate_limit_sec": 3.0,
        "hubs": {
            "NP15": "TH_NP15_GEN-APND",
            "SP15": "TH_SP15_GEN-APND",
        },
        "default_hub": "NP15",
    },
    "MISO": {
        "gridstatus_class": "MISO",
        "chunk_days": 30,
        "rate_limit_sec": 2.0,
        "hubs": {
            "INDIANA": "INDIANA.HUB",
            "MINNESOTA": "MINNESOTA.HUB",
            "ILLINOIS": "ILLINOIS.HUB",
            "LOUISIANA": "LOUISIANA.HUB",
            "ARKANSAS": "ARKANSAS.HUB",
            "TEXAS": "TEXAS.HUB",
        },
        "default_hub": "INDIANA",
    },
    "SPP": {
        "gridstatus_class": "SPP",
        "chunk_days": 30,
        "rate_limit_sec": 2.0,
        "hubs": {
            "SOUTH": "SPPSOUTH_HUB",
            "NORTH": "SPPNORTH_HUB",
        },
        "default_hub": "SOUTH",
        "disabled": True,  # SPP historical DA LMP downloads 404 as of 2026-02
    },
    "PJM": {
        "gridstatus_class": "PJM",
        "chunk_days": 30,
        "rate_limit_sec": 5.0,  # PJM rate limits aggressively
        "hubs": {
            "WESTERN": "51288",  # WESTERN HUB pnode_id
        },
        "default_hub": "WESTERN",
    },
}


class GridStatusLMPAdapter:
    """Fetch LMP data from ISO markets via gridstatus.

    Supports CAISO, MISO, SPP, and PJM. Defaults to CAISO for
    backward compatibility.
    """

    def __init__(
        self,
        rto: str = "CAISO",
        rate_limit_sec: Optional[float] = None,
    ):
        rto = rto.upper()
        if rto not in RTO_CONFIG:
            raise ValueError(f"Unsupported RTO: {rto}. Supported: {list(RTO_CONFIG)}")

        self._rto = rto
        self._config = RTO_CONFIG[rto]
        self._iso = None
        self._rate_limit_sec = rate_limit_sec or self._config["rate_limit_sec"]
        self._last_request_time = 0.0
        self._chunk_days = self._config["chunk_days"]

    def _get_iso(self):
        if self._iso is None:
            import gridstatus
            cls_name = self._config["gridstatus_class"]
            self._iso = getattr(gridstatus, cls_name)()
        return self._iso

    def _throttle(self):
        elapsed = time.time() - self._last_request_time
        if elapsed < self._rate_limit_sec:
            time.sleep(self._rate_limit_sec - elapsed)
        self._last_request_time = time.time()

    def _fetch_chunk(
        self,
        node_id: str,
        start: str,
        end: str,
        market: str = "DAY_AHEAD_HOURLY",
        max_retries: int = 3,
    ) -> pd.DataFrame:
        """Fetch LMP for a single node over a date range."""
        iso = self._get_iso()

        for attempt in range(max_retries):
            try:
                self._throttle()
                df = iso.get_lmp(
                    date=start,
                    end=end,
                    market=market,
                    locations=[node_id],
                )
                return df
            except Exception as e:
                if attempt < max_retries - 1:
                    wait = 2 ** (attempt + 1)
                    logger.warning(
                        f"Retry {attempt + 1}/{max_retries} for {self._rto}/{node_id} "
                        f"{start}->{end}: {e}. Waiting {wait}s."
                    )
                    time.sleep(wait)
                else:
                    logger.error(
                        f"Failed after {max_retries} attempts for {self._rto}/{node_id} "
                        f"{start}->{end}: {e}"
                    )
                    return pd.DataFrame()

    def fetch_node_lmp(
        self,
        node_id: str,
        start_date: date,
        end_date: date,
        market: str = "DAY_AHEAD_HOURLY",
    ) -> pd.DataFrame:
        """
        Fetch LMP data for a node over an arbitrary date range.

        Automatically chunks into bite-sized requests per RTO limits.

        Returns DataFrame with columns:
            timestamp_utc, node_id, lmp, energy_component,
            congestion_component, loss_component
        """
        all_chunks = []
        chunk_start = start_date

        while chunk_start < end_date:
            chunk_end = min(chunk_start + timedelta(days=self._chunk_days), end_date)
            logger.info(f"  Fetching {self._rto}/{node_id}: {chunk_start} to {chunk_end}")

            df = self._fetch_chunk(
                node_id,
                start=str(chunk_start),
                end=str(chunk_end),
                market=market,
            )

            if not df.empty:
                all_chunks.append(df)

            chunk_start = chunk_end

        if not all_chunks:
            return pd.DataFrame()

        combined = pd.concat(all_chunks, ignore_index=True)
        return self._normalize(combined, node_id)

    def fetch_hub_baseline(
        self,
        start_date: date,
        end_date: date,
        hub: Optional[str] = None,
    ) -> pd.DataFrame:
        """
        Fetch hub LMP for use as regional baseline.

        If hub is not specified, uses the RTO's default hub.
        Returns DataFrame with columns: timestamp_utc, node_id, lmp,
        energy_component, congestion_component, loss_component
        """
        if hub is None:
            hub = self._config["default_hub"]

        hub_node = self._config["hubs"].get(hub)
        if not hub_node:
            raise ValueError(
                f"Unknown hub '{hub}' for {self._rto}. "
                f"Available: {list(self._config['hubs'])}"
            )

        baseline_node_id = f"{self._rto}_{hub}_BASELINE"
        logger.info(f"Fetching {self._rto} {hub} baseline ({hub_node})")

        all_chunks = []
        chunk_start = start_date

        while chunk_start < end_date:
            chunk_end = min(chunk_start + timedelta(days=self._chunk_days), end_date)
            logger.info(f"  Fetching {hub_node}: {chunk_start} to {chunk_end}")

            df = self._fetch_chunk(
                hub_node,
                start=str(chunk_start),
                end=str(chunk_end),
            )

            if not df.empty:
                all_chunks.append(df)

            chunk_start = chunk_end

        if not all_chunks:
            return pd.DataFrame()

        combined = pd.concat(all_chunks, ignore_index=True)
        return self._normalize(combined, baseline_node_id)

    def _normalize(self, df: pd.DataFrame, node_id: str) -> pd.DataFrame:
        """Normalize gridstatus output to canonical schema.

        Handles column naming differences across CAISO, MISO, SPP, PJM.
        """
        if df.empty:
            return pd.DataFrame()

        out = pd.DataFrame()

        # Timestamp: gridstatus uses "Interval Start" or "Time"
        if "Interval Start" in df.columns:
            ts = pd.to_datetime(df["Interval Start"])
        elif "Time" in df.columns:
            ts = pd.to_datetime(df["Time"])
        else:
            logger.warning(f"No timestamp column found in {self._rto} data")
            return pd.DataFrame()

        # Convert to UTC if timezone-aware
        if ts.dt.tz is not None:
            ts = ts.dt.tz_convert("UTC").dt.tz_localize(None)

        out["timestamp_utc"] = ts
        out["node_id"] = node_id
        out["lmp"] = df["LMP"].astype(float)
        out["energy_component"] = df.get("Energy", pd.Series(dtype=float)).astype(float)
        out["congestion_component"] = df.get("Congestion", pd.Series(dtype=float)).astype(float)
        out["loss_component"] = df.get("Loss", pd.Series(dtype=float)).astype(float)

        # Deduplicate on timestamp (DST transitions can cause overlap)
        out = out.drop_duplicates(subset=["timestamp_utc", "node_id"], keep="first")
        out = out.sort_values("timestamp_utc").reset_index(drop=True)

        return out
