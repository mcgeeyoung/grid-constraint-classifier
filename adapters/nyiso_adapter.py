"""
New York ISO (NYISO) adapter.

NYISO provides LMP decomposition (E+C+L) but with an inverted congestion
sign convention compared to other ISOs. The adapter flips the sign
automatically via the congestion_sign_flip config flag.

NYISO only provides zone-level and generator-level pricing. There is
no bus-level (pnode) pricing, so pnode drill-down is disabled.

Data access: CSV files, no authentication required.
"""

import logging
from pathlib import Path

import pandas as pd

from .base import ISOConfig
from .gridstatus_adapter import GridstatusAdapter

logger = logging.getLogger(__name__)


class NYISOAdapter(GridstatusAdapter):
    """
    NYISO adapter using gridstatus.

    Special handling:
      - Congestion sign is flipped (handled in GridstatusAdapter._normalize_zone_lmps)
      - Node-level pricing disabled (config.has_node_level_pricing = False)
    """

    def __init__(self, config: ISOConfig, data_dir: Path):
        super().__init__(config, data_dir)

    def pull_node_lmps(
        self, zone: str, year: int, month: int, force: bool = False
    ) -> pd.DataFrame:
        """NYISO does not have bus-level pricing. Returns empty DataFrame."""
        logger.info(
            f"NYISO: no bus-level pricing available. "
            f"Skipping node LMP pull for {zone}."
        )
        return pd.DataFrame()
