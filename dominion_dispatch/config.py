"""Program constants for Dominion Virginia Power in PJM (zone DOM)."""

# PJM commercial load / LMP zone short codes (settlement geography), e.g. DOM, PEPCO, BGE.
# See ``adapters/configs/pjm.yaml`` ``zones:`` for the full list.
#
# Dominion DER **program** scope: all settlement and DA pulls in this package target **DOM**
# (Dominion Virginia Power) unless you explicitly override CLI flags for experiments.
PJM_ZONE_DOM = "DOM"

# Day-ahead hourly LMP endpoint uses Eastern Prevailing Time in PJM strings.
PJM_LMP_TIMEZONE = "US/Eastern"

# Default node type for da_hrl_lmps. Dominion DER dispatch is modeled on **LOAD**
# pricing nodes; the legacy classifier adapter used GEN for congestion hotspots.
DEFAULT_DA_NODE_LMP_TYPE = "LOAD"

# Dispatch period policy (stressed vs extreme).
#
# ``DISPATCH_STRESSED_ABS_USD_DEFAULT`` is the absolute DA congestion ($/MWh)
# above which an hour enters the optional "stressed" tier. 16.6 is the 85th
# percentile of |congestion_price_da| across all DOM LOAD pnodes over a
# 364-day window (2025-04-18 to 2026-04-17, 11.3M node-hours), rounded.
# That makes stressed roughly the top 15% of zone-wide hours, aligned with
# ``DISPATCH_EXTREME_ABS_QUANTILE_DEFAULT = 0.95`` (top 5% per-day = extreme).
# Previous value 2.0 was inherited from the zone-aggregate classifier
# (``src/constraint_classifier.py``) and produced near-continuous stressed
# activation when applied to nodal prices.
DISPATCH_STRESSED_ABS_USD_DEFAULT = 16.6
DISPATCH_EXTREME_ABS_QUANTILE_DEFAULT = 0.95
DISPATCH_STRESSED_SIGNAL_FRACTION_DEFAULT = 0.5
