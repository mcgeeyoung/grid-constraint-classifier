"""
Midcontinent ISO (MISO) adapter.

MISO provides LMP decomposition (E+C+L) via REST JSON API.
Rate limit: 100 requests per minute. gridstatus handles this.
"""

import logging
from pathlib import Path

from .base import ISOConfig
from .gridstatus_adapter import GridstatusAdapter

logger = logging.getLogger(__name__)


class MISOAdapter(GridstatusAdapter):
    """MISO adapter using gridstatus. Standard with 100/min rate limit."""

    def __init__(self, config: ISOConfig, data_dir: Path):
        super().__init__(config, data_dir)
