"""PJM implementation of the ISODriver protocol."""
from __future__ import annotations

from datetime import date
from typing import Optional

import pandas as pd

from isos.base import ISODriver, NodeMeta
from isos.pjm.client import PJMClient


class PJMDriver:
    """ISODriver for PJM. Uses the Data Miner 2 API via PJMClient."""

    iso_id = "PJM"

    def __init__(self, client: PJMClient):
        self.client = client

    def list_load_nodes(self, pricing_zone: str) -> list[NodeMeta]:
        # Bypass query_pnodes() which has a known bug (hits /pnodes, 404s).
        # Use client.query("pnode", ...) directly.
        df = self.client.query(
            "pnode",
            params={"rowCount": 50000, "startRow": 1},
        )
        # PJM `pnode` endpoint returns `pnode_type` in {BUS, AGGREGATE, LOCALE}
        # and LOAD is a `pnode_subtype`. Filter accordingly.
        mask = (df["zone"] == pricing_zone) & (df["pnode_subtype"] == "LOAD")
        sub = df[mask].copy()
        return [
            NodeMeta(
                pnode_id=str(r["pnode_id"]),
                pnode_name=str(r["pnode_name"]),
                zone=str(r["zone"]),
                pnode_type="LOAD",
            )
            for _, r in sub.iterrows()
        ]

    def fetch_da_hourly(self, operating_date: date, pricing_zone: str) -> pd.DataFrame:
        """Return one row per (pnode, hour) with LMP components.

        Thin wrapper around the existing da_hrl_lmps query used by the Dominion
        ingest today. The caller selects nodes upstream via list_load_nodes().
        """
        # The existing ingest pipeline does this work already in
        # dominion_dispatch/ingest_pjm.py; this is a convenience for the driver
        # interface. Leave actual row materialization to the ingest pipeline
        # for now; just expose the method signature.
        raise NotImplementedError(
            "fetch_da_hourly is not yet used; Dominion ingest calls the client "
            "directly. CAISO driver will be the first real implementation."
        )
