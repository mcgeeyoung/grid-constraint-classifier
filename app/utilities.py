"""Per-utility config. Loaded from utilities/<utility_id>/config.yaml."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml
from fastapi import HTTPException

_REPO = Path(__file__).resolve().parents[1]
_CONFIG_ROOT = _REPO / "utilities"


@dataclass(frozen=True)
class UtilityConfig:
    utility_id: str
    iso: str                                  # "PJM" | "CAISO" | ...
    pricing_zone: str                         # "DOM" | "DLAP_PGAE-APND" | ...
    program_name: str                         # "Virginia DER program"
    service_territory_center: tuple[float, float]
    service_territory_zoom: float
    settlement_rate_usd_per_mwh: float
    settlement_rate_description: str
    pnode_coords_path: str                    # relative to utilities/<id>/
    zones_path: str                           # relative to utilities/<id>/


@lru_cache(maxsize=32)
def load_utility(utility_id: str) -> UtilityConfig:
    path = _CONFIG_ROOT / utility_id / "config.yaml"
    if not path.is_file():
        raise HTTPException(status_code=404, detail=f"Unknown utility: {utility_id}")
    raw = yaml.safe_load(path.read_text())
    center = raw["service_territory_center"]
    return UtilityConfig(
        utility_id=raw["utility_id"],
        iso=raw["iso"],
        pricing_zone=raw["pricing_zone"],
        program_name=raw["program_name"],
        service_territory_center=(float(center[0]), float(center[1])),
        service_territory_zoom=float(raw["service_territory_zoom"]),
        settlement_rate_usd_per_mwh=float(raw["settlement_rate_usd_per_mwh"]),
        settlement_rate_description=raw["settlement_rate_description"],
        pnode_coords_path=raw.get("pnode_coords_path", "pnode_coords_full.json"),
        zones_path=raw.get("zones_path", "zones.yaml"),
    )


def utility_dir(utility_id: str) -> Path:
    return _CONFIG_ROOT / utility_id
