"""PJM implementation of the ISODriver protocol."""
from __future__ import annotations

from datetime import date, datetime, timedelta

import pandas as pd

from isos.base import ISODriver, NodeMeta  # noqa: F401  (Protocol anchor)
from isos.pjm.client import PJMClient

# Canonical output schema, mirrored from caiso/miso/nyiso drivers.
OUTPUT_COLUMNS = [
    "pnode_id_external",
    "pnode_name",
    "hour_ending_ept",
    "lmp_da",
    "energy_price_da",
    "congestion_price_da",
    "loss_price_da",
]

# PJM da_hrl_lmps column -> canonical column.
PJM_TO_CANONICAL = {
    "total_lmp_da": "lmp_da",
    "system_energy_price_da": "energy_price_da",
    "congestion_price_da": "congestion_price_da",
    "marginal_loss_price_da": "loss_price_da",
}

# Fields to request from da_hrl_lmps. Restricting fields keeps the payload
# small enough that a full DOM zone day fits inside one Data Miner page.
_DA_FIELDS = (
    "datetime_beginning_ept,pnode_id,pnode_name,"
    "total_lmp_da,system_energy_price_da,"
    "congestion_price_da,marginal_loss_price_da"
)


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
        """Fetch DA hourly LMP for all LOAD pnodes in `pricing_zone` for one day.

        Returns one row per (pnode, hour_ending_ept) with the canonical column
        set. Empty canonical frame if PJM returns no rows.
        """
        window = _format_day_window(operating_date)
        raw = self.client.query_lmps(
            datetime_beginning_ept=window,
            lmp_type="LOAD",
            zone=pricing_zone,
            fields=_DA_FIELDS,
        )
        if raw.empty:
            return pd.DataFrame(columns=OUTPUT_COLUMNS)

        return _to_canonical(raw)


def _format_day_window(operating_date: date) -> str:
    """Build the PJM `datetime_beginning_ept` window string for one full day.

    PJM accepts `M/D/YYYY HH:MMtoM/D/YYYY HH:MM` (no zero-padding required).
    HE 1..24 == HB 0..23, so the window is `00:00 to 23:00`.
    """
    d = operating_date
    return (
        f"{d.month}/{d.day}/{d.year} 00:00to"
        f"{d.month}/{d.day}/{d.year} 23:00"
    )


def _to_canonical(raw: pd.DataFrame) -> pd.DataFrame:
    """Rename PJM columns to the canonical schema and shift HB -> HE."""
    df = raw.copy()
    df = df.rename(columns=PJM_TO_CANONICAL)

    # Hour-beginning (PJM) -> hour-ending (canonical).
    hb = pd.to_datetime(df["datetime_beginning_ept"])
    df["hour_ending_ept"] = hb + timedelta(hours=1)

    df["pnode_id_external"] = df["pnode_id"].astype(str)
    df["pnode_name"] = df["pnode_name"].astype(str)

    # Coerce price columns to float; fill missing components with NaN so the
    # output schema stays stable even on partial responses.
    for canonical_col in PJM_TO_CANONICAL.values():
        if canonical_col in df.columns:
            df[canonical_col] = pd.to_numeric(df[canonical_col], errors="coerce")
        else:
            df[canonical_col] = pd.NA

    return df[OUTPUT_COLUMNS].reset_index(drop=True)
