"""
Base adapter wrapping the gridstatus library for standardized ISO data access.

gridstatus provides a unified Python API across all 7 US ISOs.
This adapter normalizes gridstatus output to canonical column names
and handles parquet caching.

Canonical columns (matching existing PJM pipeline format):
  datetime_beginning_ept -> timestamp (kept as datetime_beginning_ept for compat)
  pnode_name             -> zone code
  total_lmp_da           -> total LMP
  congestion_price_da    -> congestion component
  marginal_loss_price_da -> loss component
  system_energy_price_da -> energy component
  hour, month            -> derived from timestamp
"""

import logging
import time
from pathlib import Path
from typing import Optional

import pandas as pd

from .base import ISOAdapter, ISOConfig

logger = logging.getLogger(__name__)


class GridstatusAdapter(ISOAdapter):
    """
    Base adapter using gridstatus library for LMP data access.

    Subclasses can override _get_gridstatus_iso() for special handling
    or fall back to a custom data source.
    """

    def __init__(self, config: ISOConfig, data_dir: Path):
        super().__init__(config, data_dir)
        self._iso_instance = None

    def _get_gridstatus_iso(self):
        """
        Get the gridstatus ISO instance.

        Lazy-loaded to avoid import cost at module level.
        """
        if self._iso_instance is None:
            import gridstatus
            cls_name = self.config.gridstatus_class
            if not cls_name:
                raise ValueError(
                    f"No gridstatus_class configured for {self.config.iso_id}"
                )
            cls = getattr(gridstatus, cls_name, None)
            if cls is None:
                raise ValueError(
                    f"gridstatus has no class '{cls_name}'. "
                    f"Available: {[c for c in dir(gridstatus) if c[0].isupper()]}"
                )
            self._iso_instance = cls()
        return self._iso_instance

    def _normalize_zone_lmps(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Normalize gridstatus zone LMP output to canonical column names.

        gridstatus typically returns columns like:
          Time, Location, LMP, Energy, Congestion, Loss
        We map these to the PJM-compatible column names used by core/.
        """
        col_map = {}

        # Timestamp columns (gridstatus uses "Time" or "Interval Start")
        for candidate in ["Time", "Interval Start", "Datetime"]:
            if candidate in df.columns:
                col_map[candidate] = "datetime_beginning_ept"
                break

        # Location -> zone name
        for candidate in ["Location", "Location Name", "Zone"]:
            if candidate in df.columns:
                col_map[candidate] = "pnode_name"
                break

        # LMP components
        lmp_map = {
            "LMP": "total_lmp_da",
            "Energy": "system_energy_price_da",
            "Congestion": "congestion_price_da",
            "Loss": "marginal_loss_price_da",
        }
        for gs_col, canon_col in lmp_map.items():
            if gs_col in df.columns:
                col_map[gs_col] = canon_col

        df = df.rename(columns=col_map)

        # Ensure timestamp is datetime
        if "datetime_beginning_ept" in df.columns:
            df["datetime_beginning_ept"] = pd.to_datetime(
                df["datetime_beginning_ept"]
            )
            df["hour"] = df["datetime_beginning_ept"].dt.hour
            df["month"] = df["datetime_beginning_ept"].dt.month
            df["day_of_week"] = df["datetime_beginning_ept"].dt.dayofweek

        # Ensure numeric LMP columns
        for col in ["total_lmp_da", "system_energy_price_da",
                     "congestion_price_da", "marginal_loss_price_da"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        # Apply congestion sign flip if needed (NYISO)
        if self.config.congestion_sign_flip and "congestion_price_da" in df.columns:
            df["congestion_price_da"] = -df["congestion_price_da"]
            logger.info(f"{self.config.iso_id}: flipped congestion sign")

        return df

    def _normalize_node_lmps(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Normalize gridstatus node LMP output to canonical column names.

        Similar to zone normalization but with node ID/name columns.
        """
        col_map = {}

        # Timestamp
        for candidate in ["Time", "Interval Start", "Datetime"]:
            if candidate in df.columns:
                col_map[candidate] = "datetime_beginning_ept"
                break

        # Node identification
        for candidate in ["Location", "Location Name", "Node"]:
            if candidate in df.columns:
                col_map[candidate] = "pnode_name"
                break

        for candidate in ["Location Id", "Node ID", "Location ID"]:
            if candidate in df.columns:
                col_map[candidate] = "pnode_id"
                break

        # LMP components
        lmp_map = {
            "LMP": "total_lmp_da",
            "Energy": "system_energy_price_da",
            "Congestion": "congestion_price_da",
            "Loss": "marginal_loss_price_da",
        }
        for gs_col, canon_col in lmp_map.items():
            if gs_col in df.columns:
                col_map[gs_col] = canon_col

        df = df.rename(columns=col_map)

        # Ensure timestamp is datetime
        if "datetime_beginning_ept" in df.columns:
            df["datetime_beginning_ept"] = pd.to_datetime(
                df["datetime_beginning_ept"]
            )
            df["hour"] = df["datetime_beginning_ept"].dt.hour
            df["month"] = df["datetime_beginning_ept"].dt.month

        # Ensure numeric columns
        for col in ["total_lmp_da", "system_energy_price_da",
                     "congestion_price_da", "marginal_loss_price_da"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        # Apply congestion sign flip if needed
        if self.config.congestion_sign_flip and "congestion_price_da" in df.columns:
            df["congestion_price_da"] = -df["congestion_price_da"]

        # Add pnode_id if missing (use hash of name)
        if "pnode_id" not in df.columns and "pnode_name" in df.columns:
            df["pnode_id"] = df["pnode_name"].apply(
                lambda x: abs(hash(str(x))) % 10**8
            )

        return df

    def pull_zone_lmps(self, year: int, force: bool = False) -> pd.DataFrame:
        """
        Pull zone-level day-ahead hourly LMPs for a full year via gridstatus.

        Caches result as parquet.
        """
        cache_path = self.data_dir / "zone_lmps" / f"zone_lmps_{year}.parquet"

        if cache_path.exists() and not force:
            logger.info(f"Loading cached zone LMPs from {cache_path}")
            return pd.read_parquet(cache_path)

        iso = self._get_gridstatus_iso()

        start = pd.Timestamp(f"{year}-01-01", tz=self.config.timezone)
        end = pd.Timestamp(f"{year}-12-31 23:00", tz=self.config.timezone)

        logger.info(
            f"Pulling {self.config.iso_id} zone LMPs for {year} "
            f"via gridstatus ({self.config.gridstatus_class})"
        )

        try:
            df = iso.get_lmp(
                start=start,
                end=end,
                market="DAY_AHEAD_HOURLY",
                locations="ALL",
                location_type="zone",
            )
        except Exception as e:
            logger.error(f"gridstatus zone LMP pull failed: {e}")
            return pd.DataFrame()

        if df is None or len(df) == 0:
            logger.warning("No zone LMP data returned from gridstatus")
            return pd.DataFrame()

        df = self._normalize_zone_lmps(df)

        # Handle synthetic congestion for ERCOT
        if self.config.congestion_approximated:
            df = self._approximate_congestion(df)

        cache_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(cache_path, index=False)
        logger.info(f"Cached {len(df)} rows to {cache_path}")

        return df

    def pull_node_lmps(
        self, zone: str, year: int, month: int, force: bool = False
    ) -> pd.DataFrame:
        """
        Pull node-level LMPs for a specific zone and month via gridstatus.

        Caches result as parquet.
        """
        if not self.config.has_node_level_pricing:
            logger.info(
                f"{self.config.iso_id}: no node-level pricing, skipping"
            )
            return pd.DataFrame()

        cache_path = (
            self.data_dir / "node_lmps"
            / f"node_lmps_{zone}_{year}_{month:02d}.parquet"
        )

        if cache_path.exists() and not force:
            logger.info(f"Loading cached node LMPs from {cache_path}")
            return pd.read_parquet(cache_path)

        iso = self._get_gridstatus_iso()

        import calendar
        last_day = calendar.monthrange(year, month)[1]
        start = pd.Timestamp(f"{year}-{month:02d}-01", tz=self.config.timezone)
        end = pd.Timestamp(
            f"{year}-{month:02d}-{last_day} 23:00", tz=self.config.timezone
        )

        logger.info(f"Pulling {self.config.iso_id} node LMPs for {zone} {year}-{month:02d}")

        try:
            df = iso.get_lmp(
                start=start,
                end=end,
                market="DAY_AHEAD_HOURLY",
                locations=zone,
                location_type="zone",
            )
        except Exception as e:
            logger.error(f"gridstatus node LMP pull failed for {zone}: {e}")
            return pd.DataFrame()

        if df is None or len(df) == 0:
            logger.warning(f"No node LMP data for {zone} {year}-{month:02d}")
            return pd.DataFrame()

        df = self._normalize_node_lmps(df)

        cache_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(cache_path, index=False)
        logger.info(f"Cached {len(df)} rows to {cache_path}")

        return df

    def _approximate_congestion(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        For ISOs without LMP decomposition (ERCOT), approximate congestion
        as zone LMP minus the hourly hub average.

        Adds a congestion_approximated flag column.
        """
        if "total_lmp_da" not in df.columns:
            return df

        # Compute hub average per timestamp
        hub_avg = df.groupby("datetime_beginning_ept")["total_lmp_da"].mean()

        # Merge and compute synthetic congestion
        df = df.set_index("datetime_beginning_ept")
        df["congestion_price_da"] = df["total_lmp_da"] - hub_avg
        df["marginal_loss_price_da"] = 0.0  # Unknown
        df["system_energy_price_da"] = hub_avg  # Approximate
        df = df.reset_index()
        df["congestion_approximated"] = True

        logger.info(
            f"{self.config.iso_id}: approximated congestion as zone LMP - hub avg"
        )
        return df
