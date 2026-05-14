"""SPP implementation of the ISODriver protocol."""
from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Optional

import pandas as pd

from isos.base import ISODriver, NodeMeta  # noqa: F401  (Protocol anchor)
from isos.spp.client import SPPClient

OUTPUT_COLUMNS = [
    "pnode_id_external",
    "pnode_name",
    "hour_ending_ept",
    "lmp_da",
    "energy_price_da",
    "congestion_price_da",
    "loss_price_da",
]

# Pseudo "load zone" type used in NodeMeta returns. SPP does not publish
# load zones in the PJM/ISO-NE sense; settlement locations and hubs are
# the canonical priced points.
TYPE_SETTLEMENT_LOCATION = "SETTLEMENT LOCATION"

# System-hub aliases. The two SPP-wide hubs are the canonical reference
# prices; we accept several common spellings.
HUB_ALIASES = {
    "SPPSOUTH": "SPPSOUTH_HUB",
    "SPP_SOUTH": "SPPSOUTH_HUB",
    "SOUTH": "SPPSOUTH_HUB",
    "SPPNORTH": "SPPNORTH_HUB",
    "SPP_NORTH": "SPPNORTH_HUB",
    "NORTH": "SPPNORTH_HUB",
}


class SPPDriver:
    """ISODriver for SPP. Uses the public file-browser API via SPPClient.

    Timezone note: SPP publishes `Interval` in **Central Prevailing
    Time** (follows DST). The canonical output column is named
    `hour_ending_ept` for schema parity with the PJM/CAISO/NYISO/MISO
    drivers, but the underlying clock is CPT. Consumers crossing DST or
    joining against EPT-anchored series should treat the column as CPT
    and convert explicitly.
    """

    iso_id = "SPP"

    def __init__(self, client: Optional[SPPClient] = None):
        self.client = client or SPPClient()

    def list_load_nodes(self, pricing_zone: str) -> list[NodeMeta]:
        """Return SPP settlement locations matching `pricing_zone`.

        Matching strategy (case-insensitive):

          * `pricing_zone == "SPP"` -> all ~1,580 settlement locations.
          * `pricing_zone in HUB_ALIASES` -> the corresponding system hub
            (`SPPSOUTH_HUB` or `SPPNORTH_HUB`).
          * Exact `Settlement Location` match -> that one location.
          * Otherwise: prefix match on `Settlement Location`. `KCPL`
            returns every `KCPL*` SL; `WR` returns every `WR*` SL
            (Westar / Evergy West). Matches against the SL name with
            an optional `.` or `_` separator after the prefix.

        Snapshots the catalog from yesterday's daily file since SPP
        does not publish a standalone catalog endpoint.
        """
        snapshot_date = date.today() - timedelta(days=1)
        df = self.client.fetch_da_lmp_day(snapshot_date)
        if df.empty:
            return []

        sl = df[["Settlement Location", "BAA"]].drop_duplicates(subset=["Settlement Location"])
        sl = sl.dropna(subset=["Settlement Location"]).reset_index(drop=True)
        if sl.empty:
            return []

        matched = _match_pricing_zone(sl, pricing_zone)
        return [
            NodeMeta(
                pnode_id=str(r["Settlement Location"]),
                pnode_name=str(r["Settlement Location"]),
                zone=str(r.get("BAA") or "SPP"),
                pnode_type=TYPE_SETTLEMENT_LOCATION,
            )
            for _, r in matched.iterrows()
        ]

    def fetch_da_hourly(self, operating_date: date, pricing_zone: str) -> pd.DataFrame:
        """Fetch DA hourly LMP for the matching SL(s) on `operating_date`.

        Returns one row per (settlement_location, hour_ending_ept) with
        the canonical column set. Empty canonical frame if the day file
        is missing or `pricing_zone` doesn't match anything.
        """
        raw = self.client.fetch_da_lmp_day(operating_date)
        if raw.empty:
            return pd.DataFrame(columns=OUTPUT_COLUMNS)

        sl_catalog = raw[["Settlement Location", "BAA"]].drop_duplicates(
            subset=["Settlement Location"]
        ).dropna(subset=["Settlement Location"])
        matched = _match_pricing_zone(sl_catalog, pricing_zone)
        if matched.empty:
            return pd.DataFrame(columns=OUTPUT_COLUMNS)

        keep = set(matched["Settlement Location"].astype(str))
        sub = raw.loc[raw["Settlement Location"].astype(str).isin(keep)].copy()
        if sub.empty:
            return pd.DataFrame(columns=OUTPUT_COLUMNS)

        return _to_canonical(sub)


def _match_pricing_zone(sl: pd.DataFrame, pricing_zone: str) -> pd.DataFrame:
    """Apply the `pricing_zone` matching rules and return the surviving rows."""
    if not pricing_zone:
        return sl.iloc[0:0]
    pz = pricing_zone.strip()
    pz_upper = pz.upper()

    if pz_upper == "SPP":
        return sl

    name_upper = sl["Settlement Location"].astype(str).str.upper()

    if pz_upper in HUB_ALIASES:
        target = HUB_ALIASES[pz_upper]
        mask = name_upper == target
        return sl.loc[mask]

    # Exact match first.
    exact = sl.loc[name_upper == pz_upper]
    if not exact.empty:
        return exact

    # Prefix match: `KCPL` matches `KCPL`, `KCPL.X`, `KCPL_X`, `KCPLHUB`.
    pattern = rf"^{re.escape(pz_upper)}([._].*|\d.*|HUB.*)?$"
    mask = name_upper.str.match(pattern)
    return sl.loc[mask]


def _to_canonical(rows: pd.DataFrame) -> pd.DataFrame:
    """Translate SPP raw rows into the canonical ISODriver output shape.

    `Interval` is hour-ending CPT; we parse as naive datetime and emit
    via `hour_ending_ept` per the schema convention (see SPPDriver
    docstring on the timezone caveat).
    """
    interval = pd.to_datetime(rows["Interval"], errors="coerce")
    out = pd.DataFrame(
        {
            "pnode_id_external": rows["Settlement Location"].astype(str).values,
            "pnode_name": rows["Settlement Location"].astype(str).values,
            "hour_ending_ept": interval.values,
            "lmp_da": rows["LMP"].values,
            "energy_price_da": rows["MEC"].values,
            "congestion_price_da": rows["MCC"].values,
            "loss_price_da": rows["MLC"].values,
        }
    )
    return out[OUTPUT_COLUMNS].reset_index(drop=True)
