"""WECC balancing-authority registry.

Each entry maps a BAA code to its OASIS DGAP (Default Generation
Aggregate Pricing) node id and a human-friendly name. The 23 BAAs
listed here are the EIM/EDAM-participating BAAs that publish prices on
CAISO OASIS, plus CAISO itself.

DGAPs are the canonical aggregate price for a BAA's footprint. For
sub-BAA pricing (specific projects, hubs, transfer points) drop down
to the OASIS PRC_LMP query directly with the appropriate node id.

PGE collision warning: `PGE` in this registry is Portland General
Electric (Oregon). California PG&E is *not* a WECC external BAA --
it's inside the CAISO control area and uses CAISODriver with
pricing_zone like `DLAP_PGAE-APND`.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BAAEntry:
    code: str           # canonical BAA code, used as DGAP suffix
    dgap_node: str      # OASIS APNODE id (e.g. "DGAP_PACE-APND")
    display_name: str   # human-facing label
    aliases: tuple[str, ...] = ()  # acceptable case-insensitive synonyms


# Canonical registry. Order is informative for "all WECC" pulls.
WECC_BAAS: tuple[BAAEntry, ...] = (
    BAAEntry("CISO", "DGAP_CISO-APND", "California ISO (control area)"),
    BAAEntry("BANC", "DGAP_BANC-APND", "Balancing Authority of Northern California (SMUD)",
             aliases=("SMUD",)),
    BAAEntry("TIDC", "DGAP_TIDC-APND", "Turlock Irrigation District",
             aliases=("TURLOCK",)),
    BAAEntry("LADWP", "DGAP_LADWP-APND", "Los Angeles Department of Water & Power",
             aliases=("LADWP", "LA_DWP")),
    BAAEntry("PACE", "DGAP_PACE-APND", "PacifiCorp East",
             aliases=("PACIFICORP_EAST",)),
    BAAEntry("PACW", "DGAP_PACW-APND", "PacifiCorp West",
             aliases=("PACIFICORP_WEST",)),
    BAAEntry("PGE",  "DGAP_PGE-APND",  "Portland General Electric",
             aliases=("PORTLAND", "PGE_OR", "PORTLANDGE")),
    BAAEntry("AVA",  "DGAP_AVA-APND",  "Avista",
             aliases=("AVISTA",)),
    BAAEntry("PSEI", "DGAP_PSEI-APND", "Puget Sound Energy",
             aliases=("PUGET",)),
    BAAEntry("SCL",  "DGAP_SCL-APND",  "Seattle City Light",
             aliases=("SEATTLE_CL",)),
    BAAEntry("TPWR", "DGAP_TPWR-APND", "Tacoma Power",
             aliases=("TACOMA",)),
    BAAEntry("BPAT", "DGAP_BPAT-APND", "Bonneville Power Administration",
             aliases=("BPA", "BONNEVILLE")),
    BAAEntry("BCHA", "DGAP_BCHA-APND", "BC Hydro Authority",
             aliases=("BC_HYDRO", "BCHYDRO")),
    BAAEntry("IPCO", "DGAP_IPCO-APND", "Idaho Power",
             aliases=("IDAHO_POWER", "IDAHOPOWER")),
    BAAEntry("NWMT", "DGAP_NWMT-APND", "NorthWestern Energy Montana",
             aliases=("NORTHWESTERN", "NORTHWESTERN_MT")),
    BAAEntry("NEVP", "DGAP_NEVP-APND", "NV Energy / Nevada Power",
             aliases=("NV_ENERGY", "NEVADA_POWER", "NVE")),
    BAAEntry("AZPS", "DGAP_AZPS-APND", "Arizona Public Service",
             aliases=("APS", "ARIZONA_PS")),
    BAAEntry("SRP",  "DGAP_SRP-APND",  "Salt River Project",
             aliases=("SALT_RIVER", "SRP_AZ")),
    BAAEntry("TEPC", "DGAP_TEPC-APND", "Tucson Electric Power",
             aliases=("TUCSON", "TEP")),
    BAAEntry("PNM",  "DGAP_PNM-APND",  "Public Service of New Mexico",
             aliases=("PUBLIC_SERVICE_NM",)),
    BAAEntry("EPE",  "DGAP_EPE-APND",  "El Paso Electric",
             aliases=("EL_PASO", "ELPASO")),
    BAAEntry("WALC", "DGAP_WALC-APND", "WAPA Lower Colorado",
             aliases=("WAPA_LC", "WAPA_LOWER_COLORADO")),
    BAAEntry("AVRN", "DGAP_AVRN-APND", "Avangrid Renewables",
             aliases=("AVANGRID",)),
)

# Index for fast lookup: every code or alias -> BAAEntry.
_INDEX: dict[str, BAAEntry] = {}
for _e in WECC_BAAS:
    _INDEX[_e.code.upper()] = _e
    for _a in _e.aliases:
        _INDEX[_a.upper()] = _e

# California PG&E shouldn't be queried via WECC -- it's a CAISO LAP.
# These names route to a clear error rather than the wrong utility.
CAISO_INTERNAL_REROUTES = {
    "PG&E": "CAISODriver (try pricing_zone='DLAP_PGAE-APND')",
    "PGAE": "CAISODriver (try pricing_zone='DLAP_PGAE-APND')",
    "PG_AND_E": "CAISODriver (try pricing_zone='DLAP_PGAE-APND')",
    "SCE": "CAISODriver (try pricing_zone='DLAP_SCE-APND')",
    "SDGE": "CAISODriver (try pricing_zone='DLAP_SDGE-APND')",
    "SDG&E": "CAISODriver (try pricing_zone='DLAP_SDGE-APND')",
}


def lookup_baa(pricing_zone: str) -> BAAEntry | None:
    """Resolve a BAA code or alias to a BAAEntry. Case-insensitive."""
    if not pricing_zone:
        return None
    return _INDEX.get(pricing_zone.strip().upper())


def is_caiso_internal_label(pricing_zone: str) -> bool:
    """True if the label refers to an in-CAISO LAP (PG&E, SCE, SDG&E),
    which should route to CAISODriver, not WECCDriver."""
    if not pricing_zone:
        return False
    return pricing_zone.strip().upper() in CAISO_INTERNAL_REROUTES


def caiso_internal_hint(pricing_zone: str) -> str:
    """Helpful redirect text for the CAISO-internal labels."""
    return CAISO_INTERNAL_REROUTES.get(pricing_zone.strip().upper(), "")
