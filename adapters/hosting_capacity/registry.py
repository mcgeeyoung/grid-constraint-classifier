"""
Hosting capacity adapter registry (factory pattern).

Usage:
    adapter = get_hc_adapter("pge")
    df = adapter.pull_hosting_capacity()
"""

import logging
from pathlib import Path
from typing import Optional

from adapters.arcgis_client import ArcGISClient

from .base import HostingCapacityAdapter, UtilityHCConfig
from .arcgis_adapter import ArcGISHostingCapacityAdapter
from .exelon_adapter import ExelonHostingCapacityAdapter

logger = logging.getLogger(__name__)

CONFIGS_DIR = Path(__file__).parent / "configs"

_ADAPTER_MAP: dict[str, type[HostingCapacityAdapter]] = {
    "arcgis_feature": ArcGISHostingCapacityAdapter,
    "arcgis_map": ArcGISHostingCapacityAdapter,
    "exelon": ExelonHostingCapacityAdapter,
}


def get_hc_adapter(
    utility_code: str,
    data_dir: Optional[Path] = None,
    client: Optional[ArcGISClient] = None,
) -> HostingCapacityAdapter:
    """Get an adapter instance for a utility.

    Args:
        utility_code: Utility identifier (e.g. "pge", "pepco").
        data_dir: Base data directory. Default: project_root/data.
        client: Optional shared ArcGISClient instance.

    Returns:
        Initialized HostingCapacityAdapter.
    """
    config_path = CONFIGS_DIR / f"{utility_code}.yaml"
    if not config_path.exists():
        raise FileNotFoundError(
            f"No config for utility '{utility_code}' at {config_path}. "
            f"Available: {list_hc_utilities()}"
        )

    config = UtilityHCConfig.from_yaml(config_path)
    adapter_cls = _ADAPTER_MAP.get(
        config.data_source_type, ArcGISHostingCapacityAdapter,
    )

    if data_dir is None:
        data_dir = Path(__file__).parent.parent.parent / "data"
    if client is None:
        client = ArcGISClient()

    adapter = adapter_cls(config=config, data_dir=data_dir, arcgis_client=client)
    logger.info(
        f"Initialized {adapter_cls.__name__} for {config.utility_name} "
        f"({config.utility_code})"
    )
    return adapter


def list_hc_utilities() -> list[str]:
    """Return sorted list of configured utility codes."""
    return sorted(p.stem for p in CONFIGS_DIR.glob("*.yaml"))
