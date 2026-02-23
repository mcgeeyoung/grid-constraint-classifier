"""
Abstract base adapter and ISO configuration for multi-ISO support.

All ISO adapters implement ISOAdapter, providing a uniform interface
for pulling zone and node LMP data, regardless of the underlying
data source (gridstatus, custom API client, CSV files, etc.).
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import pandas as pd
import yaml

logger = logging.getLogger(__name__)


@dataclass
class ISOConfig:
    """Configuration for a single ISO/RTO."""
    iso_id: str                     # "pjm", "caiso", etc.
    iso_name: str                   # "PJM Interconnection"
    timezone: str                   # "US/Eastern", "US/Pacific", etc.
    peak_hours: set[int]            # e.g. {7, 8, ..., 22}
    zones: dict                     # zone_code -> {name, centroid_lat, centroid_lon, states}
    map_center: tuple[float, float] # (lat, lon) for Folium map
    map_zoom: int = 6               # Default zoom level
    has_lmp_decomposition: bool = True   # E+C+L available?
    has_node_level_pricing: bool = True  # Bus/pnode data available?
    congestion_sign_flip: bool = False   # NYISO: flip congestion sign
    congestion_approximated: bool = False  # ERCOT: synthetic congestion
    gridstatus_class: str = ""      # gridstatus class name (e.g. "PJM")
    rto_aggregates: set[str] = field(default_factory=set)
    validation_zones: dict = field(default_factory=dict)  # {zone: expected_type}
    states: list[str] = field(default_factory=list)       # States covered by ISO
    hifld_territory_oids: dict = field(default_factory=dict)  # zone -> [OIDs]
    zone_state_map: dict = field(default_factory=dict)  # zone -> primary state

    @classmethod
    def from_yaml(cls, yaml_path: Path) -> "ISOConfig":
        """Load ISO config from a YAML file."""
        with open(yaml_path) as f:
            data = yaml.safe_load(f)

        # Parse peak_hours from range notation or list
        peak_hours_raw = data.get("peak_hours", list(range(7, 23)))
        if isinstance(peak_hours_raw, dict) and "start" in peak_hours_raw:
            peak_hours = set(range(peak_hours_raw["start"], peak_hours_raw["end"]))
        else:
            peak_hours = set(peak_hours_raw)

        # Parse zones
        zones = {}
        for code, zinfo in data.get("zones", {}).items():
            zones[code] = {
                "name": zinfo.get("name", code),
                "centroid_lat": zinfo.get("centroid_lat", 0),
                "centroid_lon": zinfo.get("centroid_lon", 0),
                "states": zinfo.get("states", []),
            }

        map_center = tuple(data.get("map_center", [39.5, -78.0]))

        return cls(
            iso_id=data["iso_id"],
            iso_name=data.get("iso_name", data["iso_id"].upper()),
            timezone=data.get("timezone", "US/Eastern"),
            peak_hours=peak_hours,
            zones=zones,
            map_center=map_center,
            map_zoom=data.get("map_zoom", 6),
            has_lmp_decomposition=data.get("has_lmp_decomposition", True),
            has_node_level_pricing=data.get("has_node_level_pricing", True),
            congestion_sign_flip=data.get("congestion_sign_flip", False),
            congestion_approximated=data.get("congestion_approximated", False),
            gridstatus_class=data.get("gridstatus_class", ""),
            rto_aggregates=set(data.get("rto_aggregates", [])),
            validation_zones=data.get("validation_zones", {}),
            states=data.get("states", []),
            hifld_territory_oids=data.get("hifld_territory_oids", {}),
            zone_state_map=data.get("zone_state_map", {}),
        )

    def get_zone_centroids(self) -> dict:
        """Return zone centroids in the format expected by visualization."""
        centroids = {}
        for code, zinfo in self.zones.items():
            centroids[code] = {
                "lat": zinfo["centroid_lat"],
                "lon": zinfo["centroid_lon"],
                "name": zinfo["name"],
            }
        return centroids


class ISOAdapter(ABC):
    """
    Abstract base for ISO data adapters.

    Each adapter wraps a specific data source and provides standardized
    access to zone and node LMP data in a canonical column format.
    """

    def __init__(self, config: ISOConfig, data_dir: Path):
        self.config = config
        self.data_dir = data_dir / config.iso_id
        self.data_dir.mkdir(parents=True, exist_ok=True)

    @property
    def iso_id(self) -> str:
        return self.config.iso_id

    @abstractmethod
    def pull_zone_lmps(self, year: int, force: bool = False) -> pd.DataFrame:
        """
        Pull zone-level day-ahead hourly LMPs for a full year.

        Must return a DataFrame with at least these columns:
          - datetime_beginning_ept (or timestamp column matching config)
          - pnode_name (zone code)
          - total_lmp_da (total LMP $/MWh)
          - congestion_price_da (congestion component)
          - marginal_loss_price_da (loss component)
          - system_energy_price_da (energy component)
          - hour (0-23)
          - month (1-12)

        Caches result as parquet.
        """
        ...

    @abstractmethod
    def pull_node_lmps(
        self, zone: str, year: int, month: int, force: bool = False
    ) -> pd.DataFrame:
        """
        Pull node-level LMPs for a specific zone and month.

        Must return a DataFrame with at least:
          - datetime_beginning_ept
          - pnode_id (node identifier)
          - pnode_name (node name)
          - congestion_price_da
          - hour
        """
        ...

    def pull_node_lmps_year(
        self, zone: str, year: int, force: bool = False
    ) -> pd.DataFrame:
        """Pull node-level LMPs for a zone across all 12 months."""
        frames = []
        for month in range(1, 13):
            df = self.pull_node_lmps(zone=zone, year=year, month=month, force=force)
            if len(df) > 0:
                frames.append(df)

        if not frames:
            logger.warning(f"No node LMP data for {zone} {year}")
            return pd.DataFrame()

        combined = pd.concat(frames, ignore_index=True)
        logger.info(f"Combined {len(combined)} node LMP rows for {zone} {year}")
        return combined

    def get_zone_codes(self) -> list[str]:
        """Return list of zone codes for this ISO."""
        return list(self.config.zones.keys())

    def get_peak_hours(self) -> set[int]:
        """Return peak hours set for this ISO."""
        return self.config.peak_hours

    def pull_constrained_zone_pnodes(
        self,
        classification_summary: dict,
        year: int = 2025,
        force: bool = False,
    ) -> dict:
        """
        Pull node-level LMP data for all constrained zones.

        Returns {zone: DataFrame} for zones where T-score >= 0.5 or G-score >= 0.5.
        Skipped if the ISO does not have node-level pricing.
        """
        if not self.config.has_node_level_pricing:
            logger.info(
                f"{self.iso_id}: node-level pricing not available, "
                f"skipping pnode drill-down"
            )
            return {}

        constrained_zones = []
        zone_scores = classification_summary.get("zone_scores", [])
        for zs in zone_scores:
            t = zs.get("transmission_score", 0)
            g = zs.get("generation_score", 0)
            if t >= 0.5 or g >= 0.5:
                constrained_zones.append(zs["zone"])

        logger.info(f"Constrained zones for node drill-down: {constrained_zones}")

        zone_data = {}
        for zone in constrained_zones:
            try:
                node_lmps = self.pull_node_lmps_year(zone=zone, year=year, force=force)
                if len(node_lmps) > 0:
                    zone_data[zone] = node_lmps
                else:
                    logger.warning(f"  {zone}: no node LMP data, skipping")
            except Exception as e:
                logger.warning(f"  {zone}: failed to pull node LMP data ({e}), skipping")

        logger.info(f"Pulled node data for {len(zone_data)} zones")
        return zone_data
