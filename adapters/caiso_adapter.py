"""
California ISO (CAISO) adapter.

CAISO provides LMP decomposition (E+C+L) via OASIS REST API.
No authentication required. gridstatus handles the API directly.
"""

import logging
from pathlib import Path

from .base import ISOConfig
from .gridstatus_adapter import GridstatusAdapter

logger = logging.getLogger(__name__)


class CAISOAdapter(GridstatusAdapter):
    """CAISO adapter using gridstatus. Standard, no quirks."""

    def __init__(self, config: ISOConfig, data_dir: Path):
        super().__init__(config, data_dir)
