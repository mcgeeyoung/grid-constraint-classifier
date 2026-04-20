"""Zone taxonomy loader. Default to the legacy Dominion file for backward
compat with the CLI, but accept a ``utility_id`` for per-tenant loads from
``utilities/<utility_id>/zones.yaml``."""

from __future__ import annotations

import yaml
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Optional

_REPO = Path(__file__).resolve().parents[1]
REFDATA_PATH = _REPO / "dominion_dispatch" / "refdata" / "zones_dom.yaml"


@dataclass(frozen=True)
class Zone:
    id: str
    label: str
    description: str
    pnode_ids: tuple[str, ...]


@dataclass(frozen=True)
class ZoneIndex:
    zones: tuple[Zone, ...]
    by_pnode: dict[str, Zone]

    def by_id(self, zone_id: str) -> Optional[Zone]:
        for z in self.zones:
            if z.id == zone_id:
                return z
        return None


def _zones_path(utility_id: Optional[str] = None) -> Path:
    """Resolve the zones YAML file for a given utility.

    When ``utility_id`` is ``None`` the legacy Dominion file is returned so
    that ``dominion_dispatch/cli.py`` and other non-web callers continue to
    work without modification.
    """
    if utility_id:
        return _REPO / "utilities" / utility_id / "zones.yaml"
    return REFDATA_PATH


@lru_cache(maxsize=16)
def load_zones(utility_id: Optional[str] = None) -> ZoneIndex:
    path = _zones_path(utility_id)
    with open(path) as f:
        raw = yaml.safe_load(f)
    zones = tuple(
        Zone(
            id=z["id"],
            label=z["label"],
            description=z.get("description", ""),
            pnode_ids=tuple(str(p) for p in z["pnode_ids"]),
        )
        for z in raw["zones"]
    )
    by_pnode: dict[str, Zone] = {}
    for z in zones:
        for pid in z.pnode_ids:
            by_pnode[pid] = z
    return ZoneIndex(zones=zones, by_pnode=by_pnode)


def zone_for_pnode(idx: ZoneIndex, pnode_id: str) -> Optional[Zone]:
    return idx.by_pnode.get(str(pnode_id))
