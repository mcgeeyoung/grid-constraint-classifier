"""
Southwest Power Pool (SPP) adapter.

SPP provides LMP decomposition as MEC + MCC + MLC (Marginal Energy Cost,
Marginal Congestion Cost, Marginal Loss Cost). These map directly to
Energy, Congestion, Loss in our canonical format.

Data access: CSV downloads, no authentication required.
gridstatus handles CSV parsing.
"""

import logging
from pathlib import Path

from .base import ISOConfig
from .gridstatus_adapter import GridstatusAdapter

logger = logging.getLogger(__name__)


class SPPAdapter(GridstatusAdapter):
    """SPP adapter using gridstatus. Standard with CSV parsing."""

    def __init__(self, config: ISOConfig, data_dir: Path):
        super().__init__(config, data_dir)
