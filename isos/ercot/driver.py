"""ERCOT implementation of the ISODriver protocol.

Schema mapping (Option B -- hub-derived congestion):

  lmp_da               = SettlementPointPrice for the requested SP
  energy_price_da      = SettlementPointPrice for HB_HUBAVG (per hour)
  congestion_price_da  = lmp_da - energy_price_da   (derived)
  loss_price_da        = 0.0                         (ERCOT is lossless)

ERCOT does not publish MEC/MCC/MCL components natively; the
hub-derived congestion is what analysts compute anyway. See README
for the reasoning and limitations.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Optional

import pandas as pd

from isos.base import ISODriver, NodeMeta  # noqa: F401  (Protocol anchor)
from isos.ercot.client import ERCOTClient

OUTPUT_COLUMNS = [
    "pnode_id_external",
    "pnode_name",
    "hour_ending_ept",
    "lmp_da",
    "energy_price_da",
    "congestion_price_da",
    "loss_price_da",
]

# Reference SP used to derive the energy component. ERCOT publishes a
# day-ahead average of the trading hubs as `HB_HUBAVG`.
ENERGY_REFERENCE_SP = "HB_HUBAVG"

# Hub-name aliases. Keys are case-insensitive caller inputs; values are
# the canonical SettlementPoint id.
HUB_ALIASES = {
    "HOUSTON": "HB_HOUSTON",
    "NORTH": "HB_NORTH",
    "SOUTH": "HB_SOUTH",
    "WEST": "HB_WEST",
    "PAN": "HB_PAN",
    "PANHANDLE": "HB_PAN",
    "HUBAVG": "HB_HUBAVG",
    "BUSAVG": "HB_BUSAVG",
}

# Load-zone aliases. Same idea but for LZ_*. ERCOT has 8 zones; some
# are city-specific (CPS = San Antonio, AEN = Austin, LCRA / RAYBN =
# Lower Colorado / Rayburn).
LOAD_ZONE_ALIASES = {
    "AEN": "LZ_AEN",
    "CPS": "LZ_CPS",
    "HOUSTON_LZ": "LZ_HOUSTON",
    "LZ_HOUSTON": "LZ_HOUSTON",
    "NORTH_LZ": "LZ_NORTH",
    "SOUTH_LZ": "LZ_SOUTH",
    "WEST_LZ": "LZ_WEST",
    "LCRA": "LZ_LCRA",
    "RAYBN": "LZ_RAYBN",
    "RAYBURN": "LZ_RAYBN",
    "AUSTIN": "LZ_AEN",
    "SAN_ANTONIO": "LZ_CPS",
}

ERCOT_PSEUDO_LABEL = "ERCOT"


class ERCOTDriver:
    """ISODriver for ERCOT. Uses the public REST API via ERCOTClient.

    Timezone note: ERCOT publishes `hourEnding` as a `HH:MM` string
    valued `01:00` ... `24:00` in **Central Prevailing Time** (follows
    DST). The canonical output column is named `hour_ending_ept` for
    schema parity, but the underlying clock is CPT. `24:00` is treated
    as the next day's `00:00`.
    """

    iso_id = "ERCOT"

    def __init__(self, client: ERCOTClient):
        self.client = client

    def list_load_nodes(self, pricing_zone: str) -> list[NodeMeta]:
        """Resolve `pricing_zone` to one or more ERCOT settlement points.

        Matching rules (case-insensitive):

          * `"ERCOT"` (or empty) -> all 8 `LZ_*` load zones.
          * Hub alias (e.g. `"HOUSTON"`, `"NORTH"`, `"PAN"`) -> the
            matching `HB_*` (1 SP).
          * Load-zone alias (e.g. `"AEN"`, `"AUSTIN"`, `"CPS"`,
            `"LCRA"`, `"RAYBN"`) -> the matching `LZ_*` (1 SP).
          * Exact SP name (`LZ_HOUSTON`, `HB_NORTH`, `DC_E`, or any
            resource node like `7RNCHSLR_ALL`) -> that SP if it
            appears in yesterday's catalog snapshot.
          * Anything else -> empty list.

        Snapshots the catalog from yesterday's day file because ERCOT
        does not publish a standalone settlement-point catalog.
        """
        snapshot_date = date.today() - timedelta(days=1)
        df = self.client.fetch_dam_spp_day(snapshot_date)
        if df.empty:
            return []

        catalog = df[["settlementPoint"]].drop_duplicates().reset_index(drop=True)
        sps = catalog["settlementPoint"].astype(str)

        targets = _resolve_to_sp_names(pricing_zone, sps)
        if not targets:
            return []

        present = set(sps[sps.isin(targets)])
        return [_to_node_meta(name) for name in sorted(present)]

    def fetch_da_hourly(self, operating_date: date, pricing_zone: str) -> pd.DataFrame:
        """Fetch DA hourly SPP for the matching SP(s) on `operating_date`.

        Always also pulls `HB_HUBAVG` (in the same response since we
        download the full day file) and uses it as the energy component.
        Returns one row per (SP, hour_ending_ept) with the canonical
        column set. Empty canonical frame if `pricing_zone` doesn't
        match anything or the day file is missing.
        """
        raw = self.client.fetch_dam_spp_day(operating_date)
        if raw.empty:
            return pd.DataFrame(columns=OUTPUT_COLUMNS)

        sps = raw["settlementPoint"].astype(str)
        targets = _resolve_to_sp_names(pricing_zone, sps)
        if not targets:
            return pd.DataFrame(columns=OUTPUT_COLUMNS)

        # Always include the reference SP for the energy-component derivation.
        keep = set(targets) | {ENERGY_REFERENCE_SP}
        sub = raw.loc[sps.isin(keep)].copy()
        if sub.empty:
            return pd.DataFrame(columns=OUTPUT_COLUMNS)

        return _to_canonical(sub, operating_date, requested_targets=targets)


def _to_node_meta(sp_name: str) -> NodeMeta:
    if sp_name.startswith("LZ_"):
        ptype = "LOAD ZONE"
    elif sp_name.startswith("HB_"):
        ptype = "HUB"
    elif sp_name.startswith("DC_"):
        ptype = "DC TIE"
    else:
        ptype = "RESOURCE NODE"
    return NodeMeta(
        pnode_id=sp_name,
        pnode_name=sp_name,
        zone="ERCOT",
        pnode_type=ptype,
    )


def _resolve_to_sp_names(pricing_zone: str, available: pd.Series) -> set[str]:
    """Apply the pricing_zone matching rules and return the SP names to keep."""
    if not pricing_zone:
        return set()
    pz = pricing_zone.strip()
    pz_upper = pz.upper()

    if pz_upper == ERCOT_PSEUDO_LABEL:
        return set(available[available.astype(str).str.startswith("LZ_")].unique())

    if pz_upper in HUB_ALIASES:
        return {HUB_ALIASES[pz_upper]}
    if pz_upper in LOAD_ZONE_ALIASES:
        return {LOAD_ZONE_ALIASES[pz_upper]}

    # Exact case-insensitive match against the catalog.
    upper = available.astype(str).str.upper()
    exact = available[upper == pz_upper]
    if not exact.empty:
        return set(exact.astype(str))

    return set()


def _to_canonical(
    sub: pd.DataFrame,
    operating_date: date,
    *,
    requested_targets: set[str],
) -> pd.DataFrame:
    """Pivot ERCOT SPP rows into the canonical schema with hub-derived energy.

    `sub` already contains rows for `requested_targets` PLUS HB_HUBAVG.
    We compute, per hour:

      energy_price_da = HB_HUBAVG SPP
      lmp_da          = SP SPP
      congestion_price_da = lmp_da - energy_price_da
      loss_price_da   = 0.0

    HB_HUBAVG itself, when in `requested_targets`, naturally yields
    `congestion_price_da == 0`.
    """
    sub = sub.copy()
    he_int = sub["hourEnding"].astype(str).str[:2].astype(int)
    base = datetime.combine(operating_date, datetime.min.time())
    sub["hour_ending_ept"] = he_int.apply(lambda h: base + timedelta(hours=int(h)))
    sub["spp"] = pd.to_numeric(sub["settlementPointPrice"], errors="coerce")

    # Build a (hour_ending_ept) -> HB_HUBAVG SPP map.
    hubavg = (
        sub.loc[sub["settlementPoint"] == ENERGY_REFERENCE_SP, ["hour_ending_ept", "spp"]]
        .drop_duplicates(subset=["hour_ending_ept"])
        .rename(columns={"spp": "energy_price_da"})
    )

    # Restrict output to the requested SPs (may include HB_HUBAVG itself).
    keep = sub.loc[sub["settlementPoint"].isin(requested_targets)].copy()
    if keep.empty:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)

    merged = keep.merge(hubavg, on="hour_ending_ept", how="left")
    merged = merged.rename(
        columns={"settlementPoint": "pnode_id_external", "spp": "lmp_da"}
    )
    merged["pnode_name"] = merged["pnode_id_external"].astype(str)
    merged["congestion_price_da"] = merged["lmp_da"] - merged["energy_price_da"]
    merged["loss_price_da"] = 0.0

    return merged[OUTPUT_COLUMNS].reset_index(drop=True)
