"""
Midcontinent ISO (MISO) adapter.

Primary source: custom MISO market report client for loadzone LMPs,
aggregated to utility-area level (~43 utility prefixes).
Fallback: gridstatus (returns only 8 market hubs).
"""

import logging
from pathlib import Path

import pandas as pd

from .base import ISOConfig
from .gridstatus_adapter import GridstatusAdapter

logger = logging.getLogger(__name__)


class MISOAdapter(GridstatusAdapter):
    """
    MISO adapter with dual data source support:
      - Primary: custom MISO market report client (432 loadzones -> ~43 utility areas)
      - Fallback: gridstatus (8 market hubs)
    """

    def __init__(self, config: ISOConfig, data_dir: Path):
        super().__init__(config, data_dir)
        self._miso_client = None

    def _get_miso_client(self):
        """Lazy-load the custom MISO client."""
        if self._miso_client is None:
            from src.miso_client import MISOClient
            self._miso_client = MISOClient()
        return self._miso_client

    def pull_zone_lmps(self, year: int, force: bool = False) -> pd.DataFrame:
        """Pull MISO loadzone LMPs, preferring custom client over gridstatus."""
        cache_path = self.data_dir / "zone_lmps" / f"zone_lmps_{year}.parquet"

        if cache_path.exists() and not force:
            logger.info(f"Loading cached zone LMPs from {cache_path}")
            return pd.read_parquet(cache_path)

        # Try custom MISO client first
        try:
            return self._pull_zone_lmps_miso(year, cache_path)
        except Exception as e:
            logger.warning(f"MISO custom pull failed ({e}), falling back to gridstatus")
            return super().pull_zone_lmps(year, force=True)

    def _pull_zone_lmps_miso(
        self, year: int, cache_path: Path
    ) -> pd.DataFrame:
        """Pull loadzone LMPs and aggregate to utility-area level."""
        client = self._get_miso_client()

        logger.info(f"Pulling MISO Loadzone LMPs for {year} via custom client")

        df = client.query_lmps(
            start_date=f"{year}-01-01",
            end_date=f"{year}-12-31",
            location_type="Loadzone",
        )

        if len(df) == 0:
            logger.warning("No Loadzone LMP data returned from MISO")
            return df

        # Aggregate loadzones to utility-area level
        df = self._aggregate_to_utility_areas(df)

        # Filter to configured zones if any
        if self.config.zones and "pnode_name" in df.columns:
            configured = set(self.config.zones.keys())
            filtered = df[df["pnode_name"].isin(configured)]
            if len(filtered) > 0:
                logger.info(
                    f"Filtered to {filtered['pnode_name'].nunique()} configured "
                    f"utility areas from {df['pnode_name'].nunique()} total"
                )
                df = filtered

        cache_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(cache_path, index=False)
        logger.info(f"Cached {len(df)} rows to {cache_path}")

        return df

    def _aggregate_to_utility_areas(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Aggregate individual loadzones to utility-area level.

        MISO loadzone names follow the pattern "PREFIX.LOAD1", "PREFIX.LOAD2".
        We extract the prefix (e.g., "AMIL", "ALTE") and average across all
        loadzones sharing that prefix for each timestamp.
        """
        if "pnode_name" not in df.columns:
            return df

        # Extract utility prefix: "AMIL.LOAD1" -> "AMIL"
        df["utility_prefix"] = df["pnode_name"].str.split(".").str[0]

        # Some loadzone names don't have a dot (just "NODENAME")
        # Keep those as-is
        mask_no_dot = ~df["pnode_name"].str.contains(".", regex=False)
        df.loc[mask_no_dot, "utility_prefix"] = df.loc[mask_no_dot, "pnode_name"]

        price_cols = [
            "total_lmp_da", "congestion_price_da",
            "marginal_loss_price_da", "system_energy_price_da",
        ]
        price_cols = [c for c in price_cols if c in df.columns]

        # Group by (timestamp, utility_prefix) and average the LMP components
        agg_dict = {col: "mean" for col in price_cols}
        grouped = (
            df.groupby(["datetime_beginning_ept", "utility_prefix"])
            .agg(agg_dict)
            .reset_index()
        )

        # Replace pnode_name with utility prefix
        grouped = grouped.rename(columns={"utility_prefix": "pnode_name"})

        # Re-derive time columns
        grouped["hour"] = grouped["datetime_beginning_ept"].dt.hour
        grouped["month"] = grouped["datetime_beginning_ept"].dt.month
        grouped["day_of_week"] = grouped["datetime_beginning_ept"].dt.dayofweek

        logger.info(
            f"Aggregated {df['pnode_name'].nunique()} loadzones to "
            f"{grouped['pnode_name'].nunique()} utility areas"
        )

        return grouped
