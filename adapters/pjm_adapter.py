"""
PJM Interconnection adapter.

Falls back to the custom PJM Data Miner 2 API client if
PJM_SUBSCRIPTION_KEY is set, otherwise uses gridstatus.
"""

import logging
import os
from pathlib import Path
from typing import Optional

import pandas as pd

from .base import ISOConfig
from .gridstatus_adapter import GridstatusAdapter

logger = logging.getLogger(__name__)


class PJMAdapter(GridstatusAdapter):
    """
    PJM adapter with dual data source support:
      - Primary: custom PJM Data Miner 2 client (if API key is set)
      - Fallback: gridstatus library
    """

    def __init__(self, config: ISOConfig, data_dir: Path):
        super().__init__(config, data_dir)
        self._pjm_client = None

    def _has_api_key(self) -> bool:
        return bool(os.environ.get("PJM_SUBSCRIPTION_KEY"))

    def _get_pjm_client(self):
        """Lazy-load the custom PJM client."""
        if self._pjm_client is None:
            from src.pjm_client import PJMClient
            key = os.environ.get("PJM_SUBSCRIPTION_KEY", "")
            self._pjm_client = PJMClient(key)
        return self._pjm_client

    def pull_zone_lmps(self, year: int, force: bool = False) -> pd.DataFrame:
        """
        Pull PJM zone LMPs, preferring custom client over gridstatus.
        """
        cache_path = self.data_dir / "zone_lmps" / f"zone_lmps_{year}.parquet"

        if cache_path.exists() and not force:
            logger.info(f"Loading cached zone LMPs from {cache_path}")
            return pd.read_parquet(cache_path)

        # Use custom PJM client if API key available
        if self._has_api_key():
            return self._pull_zone_lmps_custom(year, cache_path)

        # Otherwise use gridstatus
        logger.info("No PJM_SUBSCRIPTION_KEY set, using gridstatus")
        return super().pull_zone_lmps(year, force=True)

    def _pull_zone_lmps_custom(
        self, year: int, cache_path: Path
    ) -> pd.DataFrame:
        """Pull zone LMPs using the custom PJM Data Miner 2 client."""
        client = self._get_pjm_client()
        date_range = f"1/1/{year} 00:00to12/31/{year} 23:00"

        logger.info(f"Pulling PJM zone LMPs for {year} via custom client")
        df = client.query_lmps(
            datetime_beginning_ept=date_range,
            lmp_type="ZONE",
        )

        if len(df) == 0:
            logger.warning("No zone LMP data returned from PJM API")
            return df

        # Parse datetime
        df["datetime_beginning_ept"] = pd.to_datetime(df["datetime_beginning_ept"])
        df["hour"] = df["datetime_beginning_ept"].dt.hour
        df["month"] = df["datetime_beginning_ept"].dt.month
        df["day_of_week"] = df["datetime_beginning_ept"].dt.dayofweek

        # Ensure numeric columns
        for col in ["system_energy_price_da", "total_lmp_da",
                     "congestion_price_da", "marginal_loss_price_da"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        cache_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(cache_path, index=False)
        logger.info(f"Cached {len(df)} rows to {cache_path}")

        return df

    def pull_node_lmps(
        self, zone: str, year: int, month: int, force: bool = False
    ) -> pd.DataFrame:
        """
        Pull PJM node LMPs, preferring custom client over gridstatus.
        """
        cache_path = (
            self.data_dir / "node_lmps"
            / f"node_lmps_{zone}_{year}_{month:02d}.parquet"
        )

        if cache_path.exists() and not force:
            logger.info(f"Loading cached node LMPs from {cache_path}")
            return pd.read_parquet(cache_path)

        if self._has_api_key():
            return self._pull_node_lmps_custom(zone, year, month, cache_path)

        return super().pull_node_lmps(zone, year, month, force=True)

    def _pull_node_lmps_custom(
        self, zone: str, year: int, month: int, cache_path: Path
    ) -> pd.DataFrame:
        """Pull node LMPs using the custom PJM client."""
        import calendar

        client = self._get_pjm_client()
        last_day = calendar.monthrange(year, month)[1]
        date_range = f"{month}/1/{year} 00:00to{month}/{last_day}/{year} 23:00"

        logger.info(f"Pulling PJM node LMPs for {zone} {year}-{month:02d} via custom client")
        df = client.query_lmps(
            datetime_beginning_ept=date_range,
            lmp_type="GEN",
            zone=zone,
        )

        if len(df) > 0:
            df["datetime_beginning_ept"] = pd.to_datetime(df["datetime_beginning_ept"])
            for col in ["total_lmp_da", "congestion_price_da", "marginal_loss_price_da"]:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors="coerce")

        cache_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(cache_path, index=False)
        logger.info(f"Cached {len(df)} rows to {cache_path}")

        return df
