"""
Base hosting capacity adapter and config.

Follows the same pattern as adapters/base.py (ISOConfig + ISOAdapter).
UtilityHCConfig loads from YAML; HostingCapacityAdapter is the ABC
that all utility-specific adapters implement.
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import pandas as pd
import yaml

from adapters.arcgis_client import ArcGISClient

logger = logging.getLogger(__name__)


@dataclass
class UtilityHCConfig:
    """Configuration for a single utility's hosting capacity data source."""

    utility_code: str
    utility_name: str
    iso_id: str
    states: list[str]
    data_source_type: str  # arcgis_feature, arcgis_map, exelon, custom, unavailable

    parent_company: Optional[str] = None
    requires_auth: bool = False

    # ArcGIS endpoint config
    service_url: Optional[str] = None
    layer_index: Optional[int] = None
    page_size: int = 2000
    out_sr: int = 4326

    # Field mapping: utility field name -> canonical field name
    field_map: dict[str, str] = field(default_factory=dict)

    # Unit config
    capacity_unit: str = "kw"  # "kw" or "mw"

    # URL discovery (for ComEd quarterly rotation)
    url_discovery_method: str = "static"  # static, quarterly_name, service_catalog
    url_pattern: Optional[str] = None

    @classmethod
    def from_yaml(cls, yaml_path: Path) -> "UtilityHCConfig":
        """Load config from a YAML file."""
        with open(yaml_path) as f:
            data = yaml.safe_load(f)
        valid_fields = cls.__dataclass_fields__
        return cls(**{k: v for k, v in data.items() if k in valid_fields})


class HostingCapacityAdapter(ABC):
    """Abstract base for utility hosting capacity adapters."""

    def __init__(
        self,
        config: UtilityHCConfig,
        data_dir: Path,
        arcgis_client: ArcGISClient,
    ):
        self.config = config
        self.data_dir = data_dir / "hosting_capacity" / config.utility_code
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.client = arcgis_client

    @abstractmethod
    def pull_hosting_capacity(self, force: bool = False) -> pd.DataFrame:
        """Pull and return hosting capacity data as a DataFrame.

        Implementations should handle caching via get_cache_path().
        """
        ...

    def get_cache_path(self) -> Path:
        """Path to the Parquet cache for this utility."""
        return self.data_dir / "hosting_capacity.parquet"

    def resolve_current_url(self) -> str:
        """Build the query URL from config. Override for dynamic discovery."""
        if not self.config.service_url or self.config.layer_index is None:
            raise ValueError(
                f"{self.config.utility_code}: service_url and layer_index required"
            )
        return f"{self.config.service_url}/{self.config.layer_index}/query"
