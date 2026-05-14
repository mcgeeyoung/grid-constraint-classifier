"""MISO implementation of the ISODriver protocol."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Optional

import pandas as pd

from isos.base import ISODriver, NodeMeta  # noqa: F401
from isos.miso.client import VARIANT_EXPOST, MISOClient

OUTPUT_COLUMNS = [
    "pnode_id_external",
    "pnode_name",
    "hour_ending_ept",
    "lmp_da",
    "energy_price_da",
    "congestion_price_da",
    "loss_price_da",
]

# MISO's node taxonomy from the daily CSV `Type` column.
TYPE_LOADZONE = "Loadzone"
TYPE_HUB = "Hub"
TYPE_INTERFACE = "Interface"
TYPE_GENNODE = "Gennode"

VALUE_LMP = "LMP"
VALUE_CONGESTION = "MCC"   # Marginal Congestion Component
VALUE_LOSS = "MLC"         # Marginal Loss Component

HE_COLUMNS = [f"HE {h}" for h in range(1, 25)]


class MISODriver:
    """ISODriver for MISO. Uses the docs.misoenergy.org market reports
    via MISOClient.

    Timezone note: MISO reports hour-ending in **EST year-round** (not
    EDT). The canonical output column is named `hour_ending_ept` for
    schema symmetry with the PJM/CAISO drivers; the underlying clock is
    EST. Consumers that cross DST boundaries should treat the column as
    EST and convert explicitly.
    """

    iso_id = "MISO"

    def __init__(self, client: Optional[MISOClient] = None):
        self.client = client or MISOClient()

    def list_load_nodes(self, pricing_zone: str) -> list[NodeMeta]:
        """Return all Loadzone pnodes under the given balancing-authority prefix.

        MISO loadzone names follow `PREFIX.SUBZONE` (e.g. `AECI.ALTW`,
        `CONS.BECO`). Passing `pricing_zone="AECI"` returns all loadzones
        whose Node starts with `AECI.`. An exact-match loadzone is also
        returned if it matches the prefix alone.

        Uses the most recent operating day (yesterday) to snapshot the
        catalog, since MISO does not publish a standalone node catalog.
        """
        snapshot_date = date.today() - timedelta(days=1)
        df = self.client.fetch_da_lmp_day(snapshot_date, variant=VARIANT_EXPOST)
        if df.empty or "Node" not in df.columns or "Type" not in df.columns:
            return []

        lz = df.loc[df["Type"] == TYPE_LOADZONE, ["Node", "Type"]].drop_duplicates()
        if lz.empty:
            return []

        node_str = lz["Node"].astype(str)
        prefix_match = node_str.str.startswith(f"{pricing_zone}.") | (node_str == pricing_zone)
        sub = lz.loc[prefix_match]
        return [
            NodeMeta(
                pnode_id=str(r["Node"]),
                pnode_name=str(r["Node"]),
                zone=pricing_zone,
                pnode_type=TYPE_LOADZONE.upper(),
            )
            for _, r in sub.iterrows()
        ]

    def fetch_da_hourly(self, operating_date: date, pricing_zone: str) -> pd.DataFrame:
        """Fetch DA hourly LMP for all loadzones under `pricing_zone`.

        Returns one row per (pnode, hour_ending_ept). If `pricing_zone`
        does not match any loadzone prefix, returns an empty canonical
        frame. Pass the exact Node name (e.g. `MICHIGAN.HUB`) to pull a
        single hub; the driver falls back to exact-Node match if the
        prefix scan returns nothing.
        """
        raw = self.client.fetch_da_lmp_day(operating_date, variant=VARIANT_EXPOST)
        if raw.empty or "Node" not in raw.columns:
            return pd.DataFrame(columns=OUTPUT_COLUMNS)

        node_str = raw["Node"].astype(str)
        prefix_mask = (
            (raw["Type"] == TYPE_LOADZONE)
            & (node_str.str.startswith(f"{pricing_zone}.") | (node_str == pricing_zone))
        )
        sub = raw.loc[prefix_mask].copy()
        if sub.empty:
            sub = raw.loc[node_str == pricing_zone].copy()
            if sub.empty:
                return pd.DataFrame(columns=OUTPUT_COLUMNS)

        return _to_canonical(sub, operating_date)


def _to_canonical(raw: pd.DataFrame, operating_date: date) -> pd.DataFrame:
    """Melt (Node, Value, HE 1..24) into one row per (Node, hour_ending)
    and pivot Values into the canonical price columns.
    """
    have_he = [c for c in HE_COLUMNS if c in raw.columns]
    long = raw.melt(
        id_vars=["Node", "Value"],
        value_vars=have_he,
        var_name="he_label",
        value_name="price",
    )
    long["he"] = long["he_label"].str.extract(r"HE (\d+)").astype(int)
    long["price"] = pd.to_numeric(long["price"], errors="coerce")

    wide = long.pivot_table(
        index=["Node", "he"],
        columns="Value",
        values="price",
        aggfunc="first",
    ).reset_index()
    wide.columns.name = None

    base = datetime.combine(operating_date, datetime.min.time())
    hour_ending = wide["he"].apply(lambda h: base + timedelta(hours=int(h)))

    out = pd.DataFrame(
        {
            "pnode_id_external": wide["Node"].astype(str).values,
            "pnode_name": wide["Node"].astype(str).values,
            "hour_ending_ept": hour_ending.values,
            "lmp_da": wide.get(VALUE_LMP, pd.Series([pd.NA] * len(wide))).values,
            "congestion_price_da": wide.get(
                VALUE_CONGESTION, pd.Series([pd.NA] * len(wide))
            ).values,
            "loss_price_da": wide.get(
                VALUE_LOSS, pd.Series([pd.NA] * len(wide))
            ).values,
        }
    )
    out["energy_price_da"] = out["lmp_da"] - out["congestion_price_da"] - out["loss_price_da"]
    return out[OUTPUT_COLUMNS].reset_index(drop=True)
