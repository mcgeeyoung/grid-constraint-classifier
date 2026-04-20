"""Abstract ISO driver interface. Implementations live under isos/<iso_id>/driver.py."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Protocol

import pandas as pd


@dataclass(frozen=True)
class NodeMeta:
    pnode_id: str
    pnode_name: str
    zone: str
    pnode_type: str  # "LOAD", "BUS", "AGGREGATE", "DLAP", "SUBLAP", etc.


class ISODriver(Protocol):
    """Per-ISO data access interface. Ingestion, event materialization, and
    settlement math above this layer are ISO-agnostic."""

    iso_id: str  # "PJM", "CAISO", "MISO", ...

    def list_load_nodes(self, pricing_zone: str) -> list[NodeMeta]:
        """Return all load-type nodes within the given pricing zone."""
        ...

    def fetch_da_hourly(self, operating_date: date, pricing_zone: str) -> pd.DataFrame:
        """Return one row per (pnode, hour_ending_ept) with LMP components.

        Required columns: pnode_id_external (str), pnode_name (str),
        hour_ending_ept (datetime), lmp_da (float), energy_price_da (float),
        congestion_price_da (float), loss_price_da (float).
        """
        ...
