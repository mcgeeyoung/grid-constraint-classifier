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

# Dispatch period policy (stressed vs extreme), aligned with classifier / pnode heuristics
DISPATCH_STRESSED_ABS_USD_DEFAULT = 2.0
DISPATCH_EXTREME_ABS_QUANTILE_DEFAULT = 0.95
DISPATCH_STRESSED_SIGNAL_FRACTION_DEFAULT = 0.5
