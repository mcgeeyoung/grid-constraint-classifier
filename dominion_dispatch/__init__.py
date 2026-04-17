"""
Dominion-focused tooling for a DER program keyed to PJM day-ahead (DA)
congestion prices at pricing nodes (pnodes).

Reuses ``src.pjm_client.PJMClient`` (PJM Data Miner 2, ``da_hrl_lmps``) and the
same congestion column semantics as ``core.pnode_analyzer`` (``congestion_price_da``).

This package is intentionally separate from the multi-ISO classifier pipeline:
it targets operational daily signals + device→pnode mapping rather than
annual zone classification dashboards.

Maps: ``asset_map`` builds Folium HTML of asset sites vs nodal associations under **DOM**.
"""

from dominion_dispatch.asset_map import build_dom_program_asset_nodal_map
from dominion_dispatch.config import (
    DEFAULT_DA_NODE_LMP_TYPE,
    DISPATCH_EXTREME_ABS_QUANTILE_DEFAULT,
    DISPATCH_STRESSED_ABS_USD_DEFAULT,
    DISPATCH_STRESSED_SIGNAL_FRACTION_DEFAULT,
    PJM_ZONE_DOM,
)
from dominion_dispatch.dispatch_schedule import (
    SCHEDULE_OUT_COLUMNS,
    build_dispatch_schedule,
    infer_hourly_frame_columns,
)
from dominion_dispatch.period_dispatch import apply_period_policy_to_schedule, interval_hour_ept
from dominion_dispatch.persist_schedule import (
    fetch_active_devices_for_schedule,
    fetch_hourly_dataframe_for_run,
    persist_dispatch_schedule,
)
from dominion_dispatch.pnode_coords import (
    load_pnode_coords_json,
    merge_pnode_coord_sources,
    pnode_id_to_latlon_from_definitions,
)

__all__ = [
    "PJM_ZONE_DOM",
    "DEFAULT_DA_NODE_LMP_TYPE",
    "DISPATCH_STRESSED_ABS_USD_DEFAULT",
    "DISPATCH_EXTREME_ABS_QUANTILE_DEFAULT",
    "DISPATCH_STRESSED_SIGNAL_FRACTION_DEFAULT",
    "SCHEDULE_OUT_COLUMNS",
    "build_dispatch_schedule",
    "infer_hourly_frame_columns",
    "fetch_hourly_dataframe_for_run",
    "fetch_active_devices_for_schedule",
    "persist_dispatch_schedule",
    "build_dom_program_asset_nodal_map",
    "load_pnode_coords_json",
    "merge_pnode_coord_sources",
    "pnode_id_to_latlon_from_definitions",
    "apply_period_policy_to_schedule",
    "interval_hour_ept",
]
