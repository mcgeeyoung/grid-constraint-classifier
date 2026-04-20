"""CAISO implementation of the ISODriver protocol."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Optional

import pandas as pd

from isos.base import ISODriver, NodeMeta  # noqa: F401  (ISODriver used as doc/protocol anchor)
from isos.caiso.client import CAISOClient

# CAISO CSV price column. OASIS uses `MW` for the LMP value (MWh is the
# interval size; the name is a holdover from the unified settlement
# schema). Documented in the interface spec 4.2.
PRICE_COLUMN = "MW"

# Output schema we mirror from the Dominion/PJM driver for ingest-side
# symmetry.
OUTPUT_COLUMNS = [
    "pnode_id_external",
    "pnode_name",
    "hour_ending_ept",
    "lmp_da",
    "energy_price_da",
    "congestion_price_da",
    "loss_price_da",
]

# CAISO LMP_TYPE -> output column mapping.
LMP_TYPE_TO_COL = {
    "LMP": "lmp_da",
    "MCE": "energy_price_da",
    "MCC": "congestion_price_da",
    "MCL": "loss_price_da",
}


class CAISODriver:
    """ISODriver for CAISO. Uses the OASIS public API via CAISOClient."""

    iso_id = "CAISO"

    def __init__(self, client: Optional[CAISOClient] = None):
        self.client = client or CAISOClient()

    def list_load_nodes(self, pricing_zone: str) -> list[NodeMeta]:
        """Return APNODE catalog rows matching a pricing zone.

        For PG&E we return the DLAP itself plus all SLAPs underneath.
        Matching strategy: exact APNODE_ID hit, plus any SLAP whose
        LAP_NAME associates it with PG&E. The APNODE catalog uses
        columns APNODE_ID, APNODE_NAME, LAP_NAME, APNODE_TYPE.
        """
        df = self.client.list_apnodes()
        if df.empty or "APNODE_ID" not in df.columns:
            return []

        ap_id_col = df["APNODE_ID"].astype(str)
        mask = ap_id_col == pricing_zone
        if "LAP_NAME" in df.columns:
            lap_col = df["LAP_NAME"].astype(str)
            mask = mask | lap_col.str.contains("PGE", case=False, na=False)
        else:
            mask = mask | ap_id_col.str.startswith(("PGE", "PG"))
        sub = df[mask].copy()

        out: list[NodeMeta] = []
        for _, r in sub.iterrows():
            pnode_id = str(r["APNODE_ID"])
            name = str(r.get("APNODE_NAME", pnode_id)) if "APNODE_NAME" in sub.columns else pnode_id
            pnode_type = str(r.get("APNODE_TYPE", "DLAP")) if "APNODE_TYPE" in sub.columns else "DLAP"
            out.append(
                NodeMeta(
                    pnode_id=pnode_id,
                    pnode_name=name,
                    zone=pricing_zone,
                    pnode_type=pnode_type,
                )
            )
        return out

    def fetch_da_hourly(self, operating_date: date, pricing_zone: str) -> pd.DataFrame:
        """Fetch DA hourly LMP for the given operating_date and pnode.

        Narrow demo implementation: 1-day window tied to the operating
        date, querying a single pnode (pricing_zone here is interpreted
        as the pnode_id, mirroring the CAISO convention where a DLAP
        is itself a queryable pnode). Real ingest should call
        `client.fetch_da_lmp()` directly with batches of pnodes and
        wider windows.

        Returns one row per (pnode, hour) with the canonical column set:
        pnode_id_external, pnode_name, hour_ending_ept, lmp_da,
        energy_price_da, congestion_price_da, loss_price_da.
        """
        # Query in UTC. OASIS uses GMT for the boundary timestamps; it
        # returns OPR_DT/OPR_HR in Pacific Prevailing Time regardless,
        # so we use the PPT date as the operating_date key.
        start = datetime.combine(
            operating_date, datetime.min.time(), tzinfo=timezone.utc
        )
        end = start + timedelta(days=1)
        raw = self.client.fetch_da_lmp(start, end, node=pricing_zone)

        if raw.empty:
            return pd.DataFrame(columns=OUTPUT_COLUMNS)

        # CAISO CSV stores the price in `MW`, not `VALUE`.
        if PRICE_COLUMN not in raw.columns:
            # Unexpected schema; surface a predictable empty frame
            # rather than raising so upstream ingest retries cleanly.
            return pd.DataFrame(columns=OUTPUT_COLUMNS)

        # Pick a node column that exists (NODE / NODE_ID / NODE_ID_XML).
        node_col = None
        for candidate in ("NODE", "NODE_ID", "NODE_ID_XML"):
            if candidate in raw.columns:
                node_col = candidate
                break
        if node_col is None:
            return pd.DataFrame(columns=OUTPUT_COLUMNS)

        # Pivot on LMP_TYPE so we get one row per (node, hour) with the
        # four price components as columns.
        piv = raw.pivot_table(
            index=["OPR_DT", "OPR_HR", node_col],
            columns="LMP_TYPE",
            values=PRICE_COLUMN,
            aggfunc="first",
        ).reset_index()
        piv.columns.name = None

        # Map CAISO component names to our canonical columns. Fill any
        # missing component with NaN so the output schema is stable.
        for src_name, dst_col in LMP_TYPE_TO_COL.items():
            if src_name in piv.columns:
                piv[dst_col] = piv[src_name]
            else:
                piv[dst_col] = pd.NA

        # Build hour_ending_ept. OPR_HR in CAISO is 1..24 hour-ending
        # in PPT; the Dominion schema also uses hour-ending semantics,
        # so we keep the same naming despite CAISO being PPT, not EPT.
        # We emit naive datetimes in PPT; upstream ingest is already
        # ISO-aware via the `iso_id` on the driver.
        base = datetime.combine(operating_date, datetime.min.time())
        piv["hour_ending_ept"] = piv["OPR_HR"].astype(int).apply(
            lambda h: base + timedelta(hours=h)
        )

        piv = piv.rename(columns={node_col: "pnode_id_external"})
        piv["pnode_id_external"] = piv["pnode_id_external"].astype(str)
        piv["pnode_name"] = piv["pnode_id_external"]

        return piv[OUTPUT_COLUMNS].reset_index(drop=True)
