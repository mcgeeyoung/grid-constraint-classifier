"""
Adapter registry: factory for getting the right ISO adapter.

Usage:
    adapter = get_adapter("pjm", data_dir=Path("data"))
    zone_lmps = adapter.pull_zone_lmps(year=2025)
"""

import logging
from pathlib import Path
from typing import Optional

from .base import ISOAdapter, ISOConfig

logger = logging.getLogger(__name__)

CONFIGS_DIR = Path(__file__).parent / "configs"

# Registry of adapter classes (populated by imports below)
_ADAPTER_CLASSES: dict[str, type] = {}

# All supported ISO IDs
SUPPORTED_ISOS = ["pjm", "caiso", "miso", "spp", "isone", "nyiso", "ercot"]


def register_adapter(iso_id: str, adapter_class: type):
    """Register an adapter class for an ISO ID."""
    _ADAPTER_CLASSES[iso_id] = adapter_class


def _load_adapter_classes():
    """Lazy-load adapter classes to avoid circular imports."""
    if _ADAPTER_CLASSES:
        return

    from .pjm_adapter import PJMAdapter
    from .caiso_adapter import CAISOAdapter
    from .miso_adapter import MISOAdapter
    from .spp_adapter import SPPAdapter
    from .isone_adapter import ISONEAdapter
    from .nyiso_adapter import NYISOAdapter
    from .ercot_adapter import ERCOTAdapter

    register_adapter("pjm", PJMAdapter)
    register_adapter("caiso", CAISOAdapter)
    register_adapter("miso", MISOAdapter)
    register_adapter("spp", SPPAdapter)
    register_adapter("isone", ISONEAdapter)
    register_adapter("nyiso", NYISOAdapter)
    register_adapter("ercot", ERCOTAdapter)


def get_adapter(
    iso_id: str,
    data_dir: Optional[Path] = None,
    config_override: Optional[ISOConfig] = None,
) -> ISOAdapter:
    """
    Get an adapter instance for the given ISO.

    Args:
        iso_id: ISO identifier ("pjm", "caiso", etc.)
        data_dir: Base data directory. Default: project_root/data
        config_override: Override the YAML config with a custom ISOConfig.

    Returns:
        Initialized ISOAdapter instance.
    """
    _load_adapter_classes()

    iso_id = iso_id.lower()
    if iso_id not in _ADAPTER_CLASSES:
        raise ValueError(
            f"Unknown ISO: '{iso_id}'. Supported: {list(_ADAPTER_CLASSES.keys())}"
        )

    if data_dir is None:
        data_dir = Path(__file__).parent.parent / "data"

    # Load config from YAML unless overridden
    if config_override:
        config = config_override
    else:
        yaml_path = CONFIGS_DIR / f"{iso_id}.yaml"
        if not yaml_path.exists():
            raise FileNotFoundError(f"No config file found at {yaml_path}")
        config = ISOConfig.from_yaml(yaml_path)

    adapter_cls = _ADAPTER_CLASSES[iso_id]
    adapter = adapter_cls(config=config, data_dir=data_dir)
    logger.info(f"Initialized {adapter_cls.__name__} for {config.iso_name}")
    return adapter


def list_adapters() -> list[str]:
    """Return list of supported ISO IDs."""
    _load_adapter_classes()
    return list(_ADAPTER_CLASSES.keys())
