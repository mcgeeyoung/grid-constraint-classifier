"""WECC implementation of the ISODriver protocol.

Pulls day-ahead aggregate prices for any of the 23 EIM/EDAM-participating
WECC balancing authorities from CAISO OASIS via the DGAP_<BAA> APnodes.
Shares the underlying HTTP layer with CAISODriver (both wrap CAISOClient).

This is the **regional** OASIS view. For in-CAISO LAP-level pricing
(PG&E, SCE, SDG&E SLAPs/DLAPs) use CAISODriver instead.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Optional

import pandas as pd

from isos.base import ISODriver, NodeMeta  # noqa: F401  (Protocol anchor)
from isos.caiso.client import CAISOClient
from isos.wecc.baas import (
    WECC_BAAS,
    BAAEntry,
    caiso_internal_hint,
    is_caiso_internal_label,
    lookup_baa,
)

OUTPUT_COLUMNS = [
    "pnode_id_external",
    "pnode_name",
    "hour_ending_ept",
    "lmp_da",
    "energy_price_da",
    "congestion_price_da",
    "loss_price_da",
]

# CAISO LMP_TYPE -> canonical column. Mirrors CAISODriver.
PRICE_COLUMN = "MW"
LMP_TYPE_TO_COL = {
    "LMP": "lmp_da",
    "MCE": "energy_price_da",
    "MCC": "congestion_price_da",
    "MCL": "loss_price_da",
}

# OASIS caps `node=` at 10 comma-separated values per call.
OASIS_NODE_BATCH = 10

WECC_PSEUDO_LABEL = "WECC"


class WECCDriver:
    """ISODriver for the broader WECC region via CAISO OASIS DGAPs.

    Timezone note: the canonical output column is named
    `hour_ending_ept` for schema parity, but OASIS publishes operating
    times in Pacific Prevailing Time (PPT, follows DST). Same convention
    as CAISODriver.

    PGE collision: `pricing_zone="PGE"` here resolves to **Portland
    General Electric** (Oregon), not California PG&E. Use CAISODriver
    with `pricing_zone="DLAP_PGAE-APND"` for the California utility.
    Passing `"PG&E"` / `"PGAE"` / `"SCE"` / `"SDGE"` to this driver
    raises with a redirect hint rather than guessing.
    """

    iso_id = "WECC"

    def __init__(self, client: Optional[CAISOClient] = None):
        self.client = client or CAISOClient()

    def list_load_nodes(self, pricing_zone: str) -> list[NodeMeta]:
        """Resolve `pricing_zone` to one or more BAA DGAPs.

        Matching:

          * `"WECC"` (or empty) -> all 23 BAAs.
          * BAA code (e.g. `"PACE"`, `"BANC"`, `"AZPS"`) -> 1 DGAP.
          * Alias (e.g. `"SMUD"`, `"BPA"`, `"BC_HYDRO"`,
            `"PACIFICORP_EAST"`) -> 1 DGAP.
          * In-CAISO LAP labels (`"PG&E"`, `"SCE"`, `"SDGE"`) raise
            ValueError with a CAISODriver redirect hint.
          * Anything else -> empty list.
        """
        entries = self._resolve_zone(pricing_zone)
        return [_to_node_meta(e) for e in entries]

    def fetch_da_hourly(self, operating_date: date, pricing_zone: str) -> pd.DataFrame:
        """Fetch DA hourly LMPs for the matching BAA DGAP(s).

        Uses a UTC-midnight 1-day window (inheriting the CAISODriver
        semantics; see that driver's docstring for the PPT alignment
        caveat). Batches across the OASIS 10-node cap as needed.

        Returns one row per (DGAP, hour_ending_ept) with the canonical
        column set. Empty canonical frame if `pricing_zone` doesn't
        match anything or OASIS returns no data.
        """
        entries = self._resolve_zone(pricing_zone)
        if not entries:
            return pd.DataFrame(columns=OUTPUT_COLUMNS)

        start = datetime.combine(operating_date, datetime.min.time(), tzinfo=timezone.utc)
        end = start + timedelta(days=1)

        all_raw: list[pd.DataFrame] = []
        for batch in _chunk(entries, OASIS_NODE_BATCH):
            nodes = [e.dgap_node for e in batch]
            raw = self.client.fetch_da_lmp(start, end, nodes=nodes)
            if not raw.empty:
                all_raw.append(raw)

        if not all_raw:
            return pd.DataFrame(columns=OUTPUT_COLUMNS)

        raw = pd.concat(all_raw, ignore_index=True)
        return _to_canonical(raw, operating_date)

    def _resolve_zone(self, pricing_zone: str) -> list[BAAEntry]:
        """Apply the matching rules to a pricing_zone string."""
        if not pricing_zone or pricing_zone.strip().upper() == WECC_PSEUDO_LABEL:
            return list(WECC_BAAS)

        if is_caiso_internal_label(pricing_zone):
            hint = caiso_internal_hint(pricing_zone)
            raise ValueError(
                f"{pricing_zone!r} is a CAISO-internal LAP, not a WECC external BAA. "
                f"Use {hint}."
            )

        entry = lookup_baa(pricing_zone)
        return [entry] if entry else []


def _to_node_meta(entry: BAAEntry) -> NodeMeta:
    return NodeMeta(
        pnode_id=entry.dgap_node,
        pnode_name=entry.dgap_node,
        zone=entry.code,
        pnode_type="DGAP",
    )


def _chunk(seq, n):
    for i in range(0, len(seq), n):
        yield seq[i : i + n]


def _to_canonical(raw: pd.DataFrame, operating_date: date) -> pd.DataFrame:
    """Pivot OASIS PRC_LMP rows into the canonical output schema."""
    if PRICE_COLUMN not in raw.columns:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)

    node_col = None
    for candidate in ("NODE", "NODE_ID", "NODE_ID_XML"):
        if candidate in raw.columns:
            node_col = candidate
            break
    if node_col is None:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)

    piv = raw.pivot_table(
        index=["OPR_DT", "OPR_HR", node_col],
        columns="LMP_TYPE",
        values=PRICE_COLUMN,
        aggfunc="first",
    ).reset_index()
    piv.columns.name = None

    for src_name, dst_col in LMP_TYPE_TO_COL.items():
        if src_name in piv.columns:
            piv[dst_col] = piv[src_name]
        else:
            piv[dst_col] = pd.NA

    base = datetime.combine(operating_date, datetime.min.time())
    piv["hour_ending_ept"] = piv["OPR_HR"].astype(int).apply(
        lambda h: base + timedelta(hours=h)
    )

    piv = piv.rename(columns={node_col: "pnode_id_external"})
    piv["pnode_id_external"] = piv["pnode_id_external"].astype(str)
    piv["pnode_name"] = piv["pnode_id_external"]

    return piv[OUTPUT_COLUMNS].reset_index(drop=True)
