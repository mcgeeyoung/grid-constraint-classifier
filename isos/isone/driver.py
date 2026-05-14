"""ISO-NE implementation of the ISODriver protocol."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Optional

import pandas as pd

from isos.base import ISODriver, NodeMeta  # noqa: F401  (Protocol anchor)
from isos.isone.client import ISONEClient

OUTPUT_COLUMNS = [
    "pnode_id_external",
    "pnode_name",
    "hour_ending_ept",
    "lmp_da",
    "energy_price_da",
    "congestion_price_da",
    "loss_price_da",
]

# Location-type strings used in the ISO-NE DA LMP CSV.
TYPE_LOAD_ZONE = "LOAD ZONE"
TYPE_HUB = "HUB"
TYPE_NETWORK_NODE = "NETWORK NODE"

# The eight ISO-NE load zones share the .Z. prefix (e.g. ".Z.MAINE").
LOAD_ZONE_PREFIX = ".Z."


class ISONEDriver:
    """ISODriver for ISO-NE. Uses the public DA LMP daily CSV via ISONEClient."""

    iso_id = "ISONE"

    def __init__(self, client: Optional[ISONEClient] = None):
        self.client = client or ISONEClient()

    def list_load_nodes(self, pricing_zone: str) -> list[NodeMeta]:
        """Return the matching ISO-NE load zone(s).

        ISO-NE publishes eight LOAD ZONE rows per operating day with
        canonical names like `.Z.MAINE`, `.Z.NEMASSBOST`. Match strategy:

          * `pricing_zone == "ISONE"` (or empty) -> all eight zones.
          * pricing_zone equals a PTID (e.g. `"4001"`) -> exact PTID match.
          * Otherwise: case-insensitive match against the part of the name
            after the `.Z.` prefix (e.g. `"MAINE"`, `"WCMASS"`,
            `"NEMASSBOST"`). Also matches the full `.Z.MAINE` form.

        Snapshots the load-zone catalog from yesterday's daily file since
        ISO-NE does not publish a standalone catalog endpoint.
        """
        snapshot_date = date.today() - timedelta(days=1)
        df = self.client.fetch_da_lmp_day(snapshot_date)
        if df.empty:
            return []

        zones = df.loc[df["location_type"] == TYPE_LOAD_ZONE, ["location_id", "location_name"]]
        zones = zones.drop_duplicates(subset=["location_id"]).reset_index(drop=True)
        if zones.empty:
            return []

        if not pricing_zone or pricing_zone.upper() == "ISONE":
            mask = pd.Series([True] * len(zones))
        else:
            mask = _zone_match_mask(zones, pricing_zone)

        sub = zones.loc[mask]
        return [
            NodeMeta(
                pnode_id=str(r["location_id"]),
                pnode_name=str(r["location_name"]),
                zone="ISONE",
                pnode_type=TYPE_LOAD_ZONE,
            )
            for _, r in sub.iterrows()
        ]

    def fetch_da_hourly(self, operating_date: date, pricing_zone: str) -> pd.DataFrame:
        """Fetch DA hourly LMP for the matching load zone(s) on `operating_date`.

        Returns one row per (location, hour_ending_ept) with the canonical
        column set. Empty canonical frame if the day file is missing or the
        zone doesn't match.

        `pricing_zone="ISONE"` returns all eight load zones (192 rows). A
        single-zone label (e.g. `"MAINE"`, `"NEMASSBOST"`) returns 24 rows.
        Pass an exact location name (e.g. `".H.INTERNAL_HUB"`) to pull a
        single hub by name.
        """
        raw = self.client.fetch_da_lmp_day(operating_date)
        if raw.empty:
            return pd.DataFrame(columns=OUTPUT_COLUMNS)

        if not pricing_zone or pricing_zone.upper() == "ISONE":
            sub = raw.loc[raw["location_type"] == TYPE_LOAD_ZONE].copy()
        else:
            zones = raw.loc[raw["location_type"] == TYPE_LOAD_ZONE]
            mask = _zone_match_mask(
                zones[["location_id", "location_name"]],
                pricing_zone,
            )
            matching_ids = set(zones.loc[mask, "location_id"].astype(str))
            if matching_ids:
                sub = raw.loc[raw["location_id"].astype(str).isin(matching_ids)].copy()
            else:
                # Fallback: exact-name match for hubs / network nodes pulled
                # by their full ISO-NE name.
                sub = raw.loc[raw["location_name"].astype(str) == pricing_zone].copy()

        if sub.empty:
            return pd.DataFrame(columns=OUTPUT_COLUMNS)

        return _to_canonical(sub, operating_date)


def _zone_match_mask(zones: pd.DataFrame, pricing_zone: str) -> pd.Series:
    """Match `pricing_zone` against an ISO-NE LOAD ZONE catalog frame.

    Matches by exact PTID, exact name, or case-insensitive name-suffix
    (`.Z.MAINE` -> matches `MAINE`).
    """
    pz = pricing_zone.strip()
    pz_upper = pz.upper().lstrip(".Z.")
    name = zones["location_name"].astype(str)
    ptid = zones["location_id"].astype(str)

    suffix = name.str.upper().str.replace(r"^\.Z\.", "", regex=True)
    return (ptid == pz) | (name.str.upper() == pz.upper()) | (suffix == pz_upper)


def _to_canonical(rows: pd.DataFrame, operating_date: date) -> pd.DataFrame:
    """Translate ISO-NE D-rows into the canonical ISODriver output shape."""
    he = pd.to_numeric(rows["hour_ending"], errors="coerce").astype("Int64")
    base = datetime.combine(operating_date, datetime.min.time())
    hour_ending = he.apply(
        lambda h: base + timedelta(hours=int(h)) if pd.notna(h) else pd.NaT
    )

    out = pd.DataFrame(
        {
            "pnode_id_external": rows["location_id"].astype(str).values,
            "pnode_name": rows["location_name"].astype(str).values,
            "hour_ending_ept": hour_ending.values,
            "lmp_da": rows["lmp"].values,
            "congestion_price_da": rows["congestion_component"].values,
            "loss_price_da": rows["marginal_loss_component"].values,
        }
    )
    # ISO-NE publishes the energy component directly; we keep that rather than
    # deriving it so any rounding asymmetry stays inside the source feed.
    out["energy_price_da"] = rows["energy_component"].values
    return out[OUTPUT_COLUMNS].reset_index(drop=True)
