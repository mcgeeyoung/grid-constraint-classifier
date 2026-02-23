"""
California ISO (CAISO) adapter.

Primary source: custom OASIS API client for 23 Sub-LAP LMPs.
Fallback: gridstatus (returns only 3 trading hubs).
"""

import logging
from pathlib import Path

import pandas as pd

from .base import ISOConfig
from .gridstatus_adapter import GridstatusAdapter

logger = logging.getLogger(__name__)


class CAISOAdapter(GridstatusAdapter):
    """
    CAISO adapter with dual data source support:
      - Primary: custom OASIS API client (23 Sub-LAPs)
      - Fallback: gridstatus (3 trading hubs)
    """

    def __init__(self, config: ISOConfig, data_dir: Path):
        super().__init__(config, data_dir)
        self._caiso_client = None

    def _get_caiso_client(self):
        """Lazy-load the custom CAISO OASIS client."""
        if self._caiso_client is None:
            from src.caiso_client import CAISOClient
            self._caiso_client = CAISOClient()
        return self._caiso_client

    def pull_zone_lmps(self, year: int, force: bool = False) -> pd.DataFrame:
        """Pull CAISO Sub-LAP LMPs, preferring OASIS API over gridstatus."""
        cache_path = self.data_dir / "zone_lmps" / f"zone_lmps_{year}.parquet"

        if cache_path.exists() and not force:
            logger.info(f"Loading cached zone LMPs from {cache_path}")
            return pd.read_parquet(cache_path)

        # Try custom OASIS client first
        try:
            return self._pull_zone_lmps_oasis(year, cache_path)
        except Exception as e:
            logger.warning(f"OASIS pull failed ({e}), falling back to gridstatus")
            return super().pull_zone_lmps(year, force=True)

    def _pull_zone_lmps_oasis(
        self, year: int, cache_path: Path
    ) -> pd.DataFrame:
        """Pull Sub-LAP LMPs using the custom OASIS client."""
        client = self._get_caiso_client()
        nodes = list(self.config.zones.keys())

        logger.info(
            f"Pulling CAISO Sub-LAP LMPs for {year} via OASIS "
            f"({len(nodes)} Sub-LAPs)"
        )

        df = client.query_lmps(
            start_date=f"{year}-01-01",
            end_date=f"{year}-12-31",
            nodes=nodes,
        )

        if len(df) == 0:
            logger.warning("No Sub-LAP LMP data returned from OASIS")
            return df

        # Ensure numeric columns
        for col in ["system_energy_price_da", "total_lmp_da",
                     "congestion_price_da", "marginal_loss_price_da"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        cache_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(cache_path, index=False)
        logger.info(f"Cached {len(df)} rows to {cache_path}")

        return df
