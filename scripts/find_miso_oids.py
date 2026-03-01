#!/usr/bin/env python3
"""
Query HIFLD ArcGIS FeatureServer to find OBJECTIDs for MISO utility service territories.

Outputs:
  - YAML block suitable for pasting into miso.yaml (hifld_territory_oids section)
  - JSON results saved to miso_oids_results.json
"""

import json
import time
import requests
from pathlib import Path

HIFLD_URL = (
    "https://services3.arcgis.com/OYP7N6mAJJCyH6hd/arcgis/rest/services/"
    "Electric_Retail_Service_Territories_HIFLD/FeatureServer/0/query"
)

# Each entry: (zone_code, [(search_term, state), ...], notes)
# Multiple search terms allow fallback queries.
# Entries marked 'multi' search ALL terms (for multi-state or multi-entity zones).
MISO_ZONES = [
    # --- Wisconsin ---
    ("ALTE", [("Wisconsin Power", "WI")], "Alliant Energy WI (HIFLD name: Wisconsin Power & Light)"),
    ("DPC", [], "Dairyland Power Cooperative (G&T coop, not in HIFLD retail territories)"),
    ("MGE", [("Madison Gas", "WI")], "Madison Gas & Electric"),
    ("WEC", [("Wisconsin Electric", "WI")], "WEC Energy / Wisconsin Electric Power"),
    ("WPS", [("Wisconsin Public Service", "WI")], "Wisconsin Public Service Corp"),
    ("WPPI", [("WPPI", "WI")], "WPPI Energy"),

    # --- Iowa ---
    ("ALTW", [("Interstate Power", "IA")], "Alliant Energy IA (HIFLD name: Interstate Power and Light)"),
    ("MEC", [("MidAmerican", "IA")], "MidAmerican Energy"),
    ("MPW", [], "Muscatine Power & Water (small muni, not in HIFLD)"),

    # --- Illinois ---
    # NOTE: HIFLD has only one Ameren entity (OID 2316 "AMEREN ILLINOIS COMPANY", listed under STATE=MO).
    # This appears to be the Ameren parent entity. We assign it to AMIL as the primary Ameren IL zone.
    # CILC and SIGE are sub-zones of Ameren that are now consolidated; they share this OID.
    # Union Electric (OID 1449) is the legacy Ameren Missouri entity.
    ("AMIL", [("Ameren", "MO")], "Ameren Illinois (HIFLD has Ameren under MO state code)"),
    ("BLEC", [], "Blue Star Energy (small, not in HIFLD)"),
    ("CILC", [("Ameren", "MO")], "Central IL Light Co (now part of Ameren, shares AMIL OID)"),
    ("CWLP", [("Springfield", "IL")], "City Water Light & Power, Springfield IL"),
    ("SIGE", [("Ameren", "MO")], "Ameren Southern Illinois (part of Ameren, shares AMIL OID)"),
    ("SIPC", [("Southern Illinois", "IL")], "Southern IL Electric Coop"),

    # --- Missouri ---
    ("AMMO", [("Union Electric", "MO")], "Ameren Missouri (HIFLD name: Union Electric Co)"),
    ("SWEC", [("Southwest Electric", "MO")], "SW Electric Coop MO"),

    # --- Indiana ---
    ("CIN", [("Southern Indiana Gas", "IN")], "CenterPoint Energy IN (formerly Vectren / Southern Indiana G&E)"),
    ("IPL", [("Indianapolis Power", "IN")], "Indianapolis Power & Light / AES Indiana"),
    ("NIPS", [("Northern Indiana", "IN")], "NIPSCO (Northern Indiana Pub Serv Co)"),
    ("OVEC", [], "Ohio Valley Electric (small, not in HIFLD retail territories)"),

    # --- Kentucky ---
    ("BREC", [], "Big Rivers Electric (G&T coop, not in HIFLD retail territories)"),

    # --- Michigan ---
    ("CONS", [("Consumers Energy", "MI")], "Consumers Energy"),
    ("DECO", [("DTE", "MI")], "DTE Electric Company"),
    ("MIUP", [("Upper Peninsula Power", "MI")], "Michigan Upper Peninsula (UPPC is the main IOU)"),
    ("UPPC", [("Upper Peninsula Power", "MI")], "Upper Peninsula Power Company"),

    # --- Minnesota ---
    ("EMBA", [("East Central Energy", "MN")], "East Central Energy coop"),
    ("GRE", [], "Great River Energy (G&T coop, not in HIFLD retail territories)"),
    ("HE", [("ALLETE", "MN")], "Minnesota Power / ALLETE"),
    ("MP", [("ALLETE", "MN")], "Minnesota Power (same as HE)"),
    ("NSP", [("Northern States Power", "MN")], "Northern States Power / Xcel"),
    ("OTP", [("Otter Tail", "MN")], "Otter Tail Power"),

    # --- Louisiana ---
    ("CLEC", [("Cleco", "LA")], "Cleco Power"),
    ("EES", [("Entergy Louisiana", "LA")], "Entergy Louisiana"),
    ("LAFA", [("Lafayette", "LA")], "Lafayette Utilities System"),
    ("LEPA", [], "Louisiana Energy & Power Authority (not in HIFLD)"),

    # --- Arkansas ---
    ("EAI", [("Entergy Arkansas", "AR")], "Entergy Arkansas"),
    ("SMP", [("West Memphis", "AR")], "City of West Memphis"),

    # --- Mississippi ---
    ("DEVI", [("Entergy Mississippi", "MS")], "Entergy Mississippi"),
    ("SME", [], "South Mississippi Electric (G&T, not in HIFLD retail territories)"),

    # --- Montana ---
    ("MHEB", [], "Montana-Dakota Utilities MT (not in HIFLD for MT; only in ND)"),

    # --- North Dakota ---
    ("MDU", [("Montana-Dakota", "ND")], "Montana-Dakota Utilities ND"),

    # --- South Dakota ---
    ("SCEG", [], "South Central Electric SD (no exact match in HIFLD)"),
]


def query_hifld(search_term: str, state: str) -> list[dict]:
    """Query HIFLD for utilities matching search_term in state."""
    where_clause = f"NAME LIKE '%{search_term}%' AND STATE='{state}'"
    params = {
        "where": where_clause,
        "outFields": "OBJECTID,NAME,STATE",
        "f": "json",
        "returnGeometry": "false",
    }
    try:
        resp = requests.get(HIFLD_URL, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        if "features" in data:
            return [f["attributes"] for f in data["features"]]
        elif "error" in data:
            print(f"  API error: {data['error'].get('message', data['error'])}")
            return []
        else:
            return []
    except requests.RequestException as e:
        print(f"  Request failed: {e}")
        return []


def main():
    results = {}  # zone_code -> {oids: [...], matches: [{OBJECTID, NAME, STATE}, ...]}
    not_found = []

    print("=" * 80)
    print("HIFLD OBJECTID Lookup for MISO Utility Service Territories")
    print("=" * 80)

    for zone_code, search_terms, notes in MISO_ZONES:
        print(f"\n--- {zone_code}: {notes} ---")

        if not search_terms:
            not_found.append(zone_code)
            print(f"  SKIPPED (not expected in HIFLD)")
            continue

        all_matches = []
        seen_oids = set()

        for search_term, state in search_terms:
            print(f"  Querying: NAME LIKE '%{search_term}%' AND STATE='{state}'")
            matches = query_hifld(search_term, state)

            for m in matches:
                oid = m["OBJECTID"]
                if oid not in seen_oids:
                    seen_oids.add(oid)
                    all_matches.append(m)
                    print(f"    Found: OID={oid}, NAME={m['NAME']}, STATE={m['STATE']}")

            # For single-entity zones, stop after first successful search
            if all_matches:
                break

            time.sleep(0.2)  # Rate limit

        if all_matches:
            oids = sorted([m["OBJECTID"] for m in all_matches])
            results[zone_code] = {
                "oids": oids,
                "matches": all_matches,
            }
        else:
            not_found.append(zone_code)
            print(f"  ** NOT FOUND **")

        time.sleep(0.15)  # Rate limit between zones

    # Save JSON results
    output_path = Path(__file__).parent / "miso_oids_results.json"
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\n\nJSON results saved to: {output_path}")

    # Print YAML output
    print("\n" + "=" * 80)
    print("YAML OUTPUT (for miso.yaml hifld_territory_oids section)")
    print("=" * 80)
    print()

    # Order by state groups matching miso.yaml zone ordering
    yaml_order = [
        # Wisconsin
        "ALTE", "DPC", "MGE", "WEC", "WPS", "WPPI",
        # Iowa
        "ALTW", "MEC", "MPW",
        # Illinois
        "AMIL", "BLEC", "CILC", "CWLP", "SIGE", "SIPC",
        # Missouri
        "AMMO", "SWEC",
        # Indiana
        "CIN", "IPL", "NIPS", "OVEC",
        # Kentucky
        "BREC",
        # Michigan
        "CONS", "DECO", "MIUP", "UPPC",
        # Minnesota
        "EMBA", "GRE", "HE", "MP", "NSP", "OTP",
        # Louisiana
        "CLEC", "EES", "LAFA", "LEPA",
        # Arkansas
        "EAI", "SMP",
        # Mississippi
        "DEVI", "SME",
        # Montana
        "MHEB",
        # North Dakota
        "MDU",
        # South Dakota
        "SCEG",
    ]

    print("hifld_territory_oids:")

    current_state_group = None
    state_groups = {
        "ALTE": "Wisconsin", "DPC": "Wisconsin", "MGE": "Wisconsin", "WEC": "Wisconsin",
        "WPS": "Wisconsin", "WPPI": "Wisconsin",
        "ALTW": "Iowa", "MEC": "Iowa", "MPW": "Iowa",
        "AMIL": "Illinois", "BLEC": "Illinois", "CILC": "Illinois", "CWLP": "Illinois",
        "SIGE": "Illinois", "SIPC": "Illinois",
        "AMMO": "Missouri", "SWEC": "Missouri",
        "CIN": "Indiana", "IPL": "Indiana", "NIPS": "Indiana", "OVEC": "Indiana",
        "BREC": "Kentucky",
        "CONS": "Michigan", "DECO": "Michigan", "MIUP": "Michigan", "UPPC": "Michigan",
        "EMBA": "Minnesota", "GRE": "Minnesota", "HE": "Minnesota", "MP": "Minnesota",
        "NSP": "Minnesota", "OTP": "Minnesota",
        "CLEC": "Louisiana", "EES": "Louisiana", "LAFA": "Louisiana", "LEPA": "Louisiana",
        "EAI": "Arkansas", "SMP": "Arkansas",
        "DEVI": "Mississippi", "SME": "Mississippi",
        "MHEB": "Montana",
        "MDU": "North Dakota",
        "SCEG": "South Dakota",
    }

    for zone in yaml_order:
        group = state_groups.get(zone, "")
        if group != current_state_group:
            current_state_group = group
            print(f"  # --- {group} ---")

        if zone in results:
            oids = results[zone]["oids"]
            names = [m["NAME"] for m in results[zone]["matches"]]
            name_str = "; ".join(names[:3])
            if len(names) > 3:
                name_str += f" (+{len(names)-3} more)"
            print(f"  {zone}: {oids}  # {name_str}")
        elif zone in not_found:
            print(f"  # {zone}: not found in HIFLD")

    # Summary
    print(f"\n  # Found: {len(results)} zones")
    print(f"  # Not found: {len(not_found)} zones: {', '.join(not_found)}")


if __name__ == "__main__":
    main()
