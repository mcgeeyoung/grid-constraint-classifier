"""NYISO implementation of the ISODriver protocol."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Optional

import pandas as pd

from isos.base import ISODriver, NodeMeta  # noqa: F401
from isos.nyiso.client import FEED_GEN, FEED_ZONE, NYISOClient

OUTPUT_COLUMNS = [
    "pnode_id_external",
    "pnode_name",
    "hour_ending_ept",
    "lmp_da",
    "energy_price_da",
    "congestion_price_da",
    "loss_price_da",
]

# NYISO's 11 load zones (the real pricing zones). The remaining four
# names in the zonal CSV (H Q, NPX, O H, PJM) are external proxy
# generators, not load zones.
LOAD_ZONES = frozenset({
    "CAPITL", "CENTRL", "DUNWOD", "GENESE", "HUD VL",
    "LONGIL", "MHK VL", "MILLWD", "N.Y.C.", "NORTH", "WEST",
})

# Raw NYISO columns. Space and punctuation are significant.
COL_TIME = "Time Stamp"
COL_NAME = "Name"
COL_PTID = "PTID"
COL_LBMP = "LBMP ($/MWHr)"
COL_LOSSES = "Marginal Cost Losses ($/MWHr)"
COL_CONGESTION = "Marginal Cost Congestion ($/MWHr)"


class NYISODriver:
    """ISODriver for NYISO. Uses the MIS public CSV feeds via NYISOClient.

    Congestion sign convention: NYISO's CSV reports `Marginal Cost
    Congestion` with the same sign convention as PJM/CAISO's congestion
    component (positive = congestion cost at the sink). We pass it
    through unchanged. The older `adapters/nyiso_adapter.py` flipped the
    sign when going through `gridstatus`, because that wrapper inverted
    it; the raw MIS CSV does not need the flip. See README for refs.
    """

    iso_id = "NYISO"

    def __init__(self, client: Optional[NYISOClient] = None):
        self.client = client or NYISOClient()

    def list_load_nodes(self, pricing_zone: str) -> list[NodeMeta]:
        """Return the NYISO load zone matching `pricing_zone`, if any.

        NYISO does not publish sub-zonal load pricing. Each load zone IS
        the load node, so this returns at most one NodeMeta. The zone
        name is matched case-sensitively against NYISO's canonical
        spelling (e.g. `N.Y.C.`, `HUD VL`, `MHK VL`).
        """
        if pricing_zone not in LOAD_ZONES:
            return []

        cat = self.client.list_zone_ptids()
        if cat.empty:
            return []
        row = cat.loc[cat["Name"] == pricing_zone]
        if row.empty:
            return []
        ptid = str(row.iloc[0]["PTID"])
        return [
            NodeMeta(
                pnode_id=ptid,
                pnode_name=pricing_zone,
                zone=pricing_zone,
                pnode_type="ZONE",
            )
        ]

    def fetch_da_hourly(self, operating_date: date, pricing_zone: str) -> pd.DataFrame:
        """Fetch DA hourly LBMP for one NYISO zone.

        Returns one row per (zone, hour_ending_ept) with the canonical
        7-column schema. Hour-ending is derived by adding one hour to
        NYISO's hour-beginning Time Stamp.
        """
        raw = self.client.fetch_da_lbmp_day(operating_date, feed=FEED_ZONE)
        if raw.empty or COL_TIME not in raw.columns:
            return pd.DataFrame(columns=OUTPUT_COLUMNS)

        sub = raw.loc[raw[COL_NAME] == pricing_zone].copy()
        if sub.empty:
            return pd.DataFrame(columns=OUTPUT_COLUMNS)

        return _to_canonical(sub, pricing_zone_as_name=pricing_zone)

    def fetch_da_hourly_buses(
        self, operating_date: date, pnode_names: list[str]
    ) -> pd.DataFrame:
        """Fetch DA hourly LBMP for specific generator pnodes.

        Non-protocol helper for bus-level pulls. NYISO exposes generator
        bus pricing only (no load-bus pnodes), so `pnode_names` here are
        generator names from the `_gen` feed (e.g. `RAVENSWOOD_GT_1`).
        """
        raw = self.client.fetch_da_lbmp_day(operating_date, feed=FEED_GEN)
        if raw.empty or COL_TIME not in raw.columns:
            return pd.DataFrame(columns=OUTPUT_COLUMNS)

        wanted = set(pnode_names)
        sub = raw.loc[raw[COL_NAME].isin(wanted)].copy()
        if sub.empty:
            return pd.DataFrame(columns=OUTPUT_COLUMNS)
        return _to_canonical(sub)


def _to_canonical(
    raw: pd.DataFrame,
    *,
    pricing_zone_as_name: Optional[str] = None,
) -> pd.DataFrame:
    """Map the raw NYISO CSV shape to the canonical 7-column output."""
    # Parse hour-beginning EPT timestamp, then shift to hour-ending.
    ts = pd.to_datetime(raw[COL_TIME], format="%m/%d/%Y %H:%M", errors="coerce")
    hour_ending = ts + pd.Timedelta(hours=1)

    lbmp = pd.to_numeric(raw[COL_LBMP], errors="coerce")
    losses = pd.to_numeric(raw[COL_LOSSES], errors="coerce")
    congestion = pd.to_numeric(raw[COL_CONGESTION], errors="coerce")
    energy = lbmp - losses - congestion

    out = pd.DataFrame(
        {
            "pnode_id_external": raw[COL_PTID].astype(str).values,
            "pnode_name": (
                [pricing_zone_as_name] * len(raw)
                if pricing_zone_as_name is not None
                else raw[COL_NAME].astype(str).values
            ),
            "hour_ending_ept": hour_ending.values,
            "lmp_da": lbmp.values,
            "energy_price_da": energy.values,
            "congestion_price_da": congestion.values,
            "loss_price_da": losses.values,
        }
    )
    return out.reset_index(drop=True)
