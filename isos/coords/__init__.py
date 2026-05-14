"""Pricing-node coordinate resolvers, shared across ISOs.

Three building blocks:

* `hifld.HifldLookup` -- load + normalized index of the national HIFLD
  Electric Substations dataset (~78,000 substations, US + Canada + Mexico).
* `match.match_pnode_names_to_hifld` -- generic matcher that takes a
  catalog of (pnode_id, pnode_name) pairs and returns
  `{pnode_id: (lat, lon)}`. Per-ISO callers supply a `normalize_name`
  function that extracts the substation token from each ISO's pnode
  naming convention.
* `match.write_coord_json` -- emit the coords JSON in the shape that
  `dominion_dispatch.pnode_coords.load_pnode_coords_json` understands.
"""
from isos.coords.hifld import HifldLookup, default_hifld_path
from isos.coords.match import match_pnode_names_to_hifld, write_coord_json

__all__ = [
    "HifldLookup",
    "default_hifld_path",
    "match_pnode_names_to_hifld",
    "write_coord_json",
]
