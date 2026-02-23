"""
Electric Reliability Council of Texas (ERCOT) adapter.

ERCOT does NOT provide LMP decomposition (no separate E+C+L components).
Only total settlement point prices (SPPs) are available.

This adapter approximates congestion as: zone LMP - hub average LMP.
Results are flagged as "congestion_approximated" in the output.

Data access: REST API with token authentication.
"""

import logging
from pathlib import Path

import pandas as pd

from .base import ISOConfig
from .gridstatus_adapter import GridstatusAdapter

logger = logging.getLogger(__name__)


class ERCOTAdapter(GridstatusAdapter):
    """
    ERCOT adapter using gridstatus.

    Special handling:
      - No LMP decomposition: congestion is approximated as zone - hub avg
      - Limited node coverage (~1K settlement points)
      - Results flagged as congestion_approximated
    """

    def __init__(self, config: ISOConfig, data_dir: Path):
        super().__init__(config, data_dir)

    def pull_zone_lmps(self, year: int, force: bool = False) -> pd.DataFrame:
        """
        Pull ERCOT zone SPPs and approximate congestion components.

        Since ERCOT has no E+C+L decomposition, we compute:
          congestion = zone_spp - hourly_hub_average
          energy = hourly_hub_average (approximation)
          loss = 0 (unknown)
        """
        df = super().pull_zone_lmps(year, force)

        if len(df) > 0 and self.config.congestion_approximated:
            # Add flag for downstream consumers
            if "congestion_approximated" not in df.columns:
                df["congestion_approximated"] = True

            logger.info(
                "ERCOT: congestion values are APPROXIMATED "
                "(zone SPP - hub average). Use with caution."
            )

        return df
