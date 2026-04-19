"""Zone taxonomy for Dominion DER program: loads ``refdata/zones_dom.yaml``
and provides pnode -> zone lookups."""

from __future__ import annotations

import yaml
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Optional

REFDATA_PATH = Path(__file__).resolve().parent / "refdata" / "zones_dom.yaml"


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


@lru_cache(maxsize=1)
def load_zones(path: Path = REFDATA_PATH) -> ZoneIndex:
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
