"""
ISO New England (ISO-NE) adapter.

ISO-NE provides LMP decomposition (E+C+L) via REST API.
Requires HTTP Basic authentication (username/password).

Set environment variables:
  ISONE_USERNAME
  ISONE_PASSWORD
"""

import logging
import os
from pathlib import Path

import pandas as pd

from .base import ISOConfig
from .gridstatus_adapter import GridstatusAdapter

logger = logging.getLogger(__name__)


class ISONEAdapter(GridstatusAdapter):
    """
    ISO-NE adapter using gridstatus.

    gridstatus handles the HTTP Basic auth internally when
    ISO-NE credentials are available.
    """

    def __init__(self, config: ISOConfig, data_dir: Path):
        super().__init__(config, data_dir)

    def _check_credentials(self):
        """Log a warning if ISO-NE credentials are not set."""
        username = os.environ.get("ISONE_USERNAME", "")
        password = os.environ.get("ISONE_PASSWORD", "")
        if not username or not password:
            logger.warning(
                "ISO-NE credentials not set. Set ISONE_USERNAME and "
                "ISONE_PASSWORD environment variables. gridstatus may "
                "fall back to public endpoints with limited data."
            )
            return False
        return True

    def pull_zone_lmps(self, year: int, force: bool = False) -> pd.DataFrame:
        self._check_credentials()
        return super().pull_zone_lmps(year, force)

    def pull_node_lmps(self, zone: str, year: int, month: int, force: bool = False) -> pd.DataFrame:
        self._check_credentials()
        return super().pull_node_lmps(zone, year, month, force)
