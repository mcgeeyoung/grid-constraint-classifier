"""
Data center scraper for interconnection.fyi.

Scrapes PJM-state data center listings, maps to PJM zones via grid operator,
geocodes addresses, and aggregates for dashboard/map integration.
"""

import json
import logging
import re
import random
import time
from pathlib import Path
from typing import Optional

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent / "data"
DC_CACHE_DIR = DATA_DIR / "data_centers"
GEO_CACHE_DIR = DATA_DIR / "geo"

DC_LISTINGS_CACHE = DC_CACHE_DIR / "dc_state_listings.json"
DC_DETAILS_CACHE = DC_CACHE_DIR / "dc_details.json"
DC_COMBINED_CACHE = DC_CACHE_DIR / "dc_combined.json"
DC_COORDINATES_CACHE = GEO_CACHE_DIR / "dc_coordinates.json"

BASE_URL = "https://www.interconnection.fyi"

# State two-letter codes used in interconnection.fyi URLs: /data-center/state/{CODE}
PJM_STATES = [
    "VA", "OH", "IL", "NJ", "IN",
    "MD", "PA", "NC", "TN",
    "DE", "MI", "WV", "DC", "KY",
]

# Map grid operator strings from interconnection.fyi to PJM zone codes.
# Operators that are not in PJM map to None and will be filtered out.
GRID_OPERATOR_TO_ZONE = {
    # Dominion
    "dominion energy virginia": "DOM",
    "dominion energy": "DOM",
    "dominion virginia power": "DOM",
    # PECO
    "peco energy": "PECO",
    "peco": "PECO",
    # PPL
    "ppl electric": "PPL",
    "ppl electric utilities": "PPL",
    "ppl": "PPL",
    # PSEG
    "pseg": "PSEG",
    "public service electric and gas": "PSEG",
    "public service electric & gas": "PSEG",
    "pse&g": "PSEG",
    # BGE
    "baltimore gas and electric": "BGE",
    "baltimore gas & electric": "BGE",
    "bge": "BGE",
    # Pepco
    "pepco": "PEPCO",
    "potomac electric power": "PEPCO",
    "potomac electric power company": "PEPCO",
    # AEP
    "american electric power": "AEP",
    "appalachian power": "AEP",
    "aep": "AEP",
    "aep ohio": "AEP",
    "indiana michigan power": "AEP",
    # ComEd
    "commonwealth edison": "COMED",
    "comed": "COMED",
    "exelon": "COMED",
    # FirstEnergy zones
    "firstenergy": "ATSI",
    "ohio edison": "ATSI",
    "the illuminating company": "ATSI",
    "toledo edison": "ATSI",
    "jersey central power & light": "JCPL",
    "jersey central power and light": "JCPL",
    "jcpl": "JCPL",
    "met-ed": "METED",
    "metropolitan edison": "METED",
    "penelec": "PENELEC",
    "penn power": "PENELEC",
    "west penn power": "APS",
    "allegheny power": "APS",
    "monongahela power": "APS",
    "potomac edison": "APS",
    # Delmarva
    "delmarva power": "DPL",
    "delmarva power & light": "DPL",
    # AECO
    "atlantic city electric": "AECO",
    # Duquesne
    "duquesne light": "DUQ",
    # Dayton
    "dayton power and light": "DAY",
    "dayton power & light": "DAY",
    "aes ohio": "DAY",
    # Duke (Ohio/KY in PJM)
    "duke energy ohio": "DEOK",
    "duke energy kentucky": "DEOK",
    "duke energy indiana": "AEP",
    # EKPC
    "east kentucky power": "EKPC",
    "east kentucky power cooperative": "EKPC",
    # Rockland
    "rockland electric": "RECO",
    "orange and rockland": "RECO",
    # AEP subsidiaries
    "ohio power co": "AEP",
    "ohio power": "AEP",
    "indiana michigan power": "AEP",
    "i&m": "AEP",
    # Dominion-territory cooperatives (served within DOM zone)
    "rappahannock electric cooperative": "DOM",
    "northern virginia electric cooperative": "DOM",
    "manassas electric system": "DOM",
    # Dayton / AES
    "aes/dp&l": "DAY",
    # Non-PJM operators (filter out)
    "duke energy carolinas": None,
    "duke energy progress": None,
    "duke energy": None,
    "tennessee valley authority": None,
    "tva": None,
    "ameren": None,
    "ameren illinois": None,
    "midamerican energy": None,
    "dte energy": None,
    "consumers energy": None,
    "indiana utility regulatory commission": None,
    "indianapolis power and light": None,
    "indianapolis power & light": None,
    "aes indiana": None,
    "vectren": None,
    "centerpoint energy": None,
    "entergy": None,
    "northern indiana public service": None,
    "nipsco": None,
    "hoosier energy": None,
}

# Substring fallback: keyword -> zone (checked if exact match fails)
_OPERATOR_SUBSTRING_MAP = {
    "dominion": "DOM",
    "peco": "PECO",
    "ppl": "PPL",
    "pseg": "PSEG",
    "pse&g": "PSEG",
    "baltimore gas": "BGE",
    "bge": "BGE",
    "pepco": "PEPCO",
    "potomac electric": "PEPCO",
    "american electric": "AEP",
    "appalachian": "AEP",
    "aep": "AEP",
    "commonwealth edison": "COMED",
    "comed": "COMED",
    "exelon": "COMED",
    "firstenergy": "ATSI",
    "ohio edison": "ATSI",
    "illuminating": "ATSI",
    "toledo edison": "ATSI",
    "jersey central": "JCPL",
    "met-ed": "METED",
    "metropolitan edison": "METED",
    "penelec": "PENELEC",
    "delmarva": "DPL",
    "atlantic city": "AECO",
    "duquesne": "DUQ",
    "dayton power": "DAY",
    "aes ohio": "DAY",
    "duke energy ohio": "DEOK",
    "duke energy kentucky": "DEOK",
    "east kentucky": "EKPC",
    "rockland": "RECO",
    "ohio power": "AEP",
    "rappahannock": "DOM",
}

# Capacity range strings -> MW midpoint estimates
CAPACITY_MIDPOINTS = {
    "< 10 mw": 5,
    "<10 mw": 5,
    "10-25 mw": 17,
    "10 - 25 mw": 17,
    "25-50 mw": 37,
    "25 - 50 mw": 37,
    "10-50 mw": 30,
    "10 - 50 mw": 30,
    "50-100 mw": 75,
    "50 - 100 mw": 75,
    "100-250 mw": 175,
    "100 - 250 mw": 175,
    "250+ mw": 375,
    "250 + mw": 375,
    ">250 mw": 375,
    "unknown": 0,
    "": 0,
}

# Zone centroids (same as data_acquisition.py) for geocoding fallback
_ZONE_CENTROIDS = {
    "AECO": (39.45, -74.75), "AEP": (38.80, -82.00),
    "APS": (40.00, -79.50), "ATSI": (41.10, -81.50),
    "BGE": (39.30, -76.60), "COMED": (41.85, -87.90),
    "DAY": (39.76, -84.19), "DEOK": (39.10, -84.50),
    "DOM": (37.55, -78.00), "DPL": (39.15, -75.52),
    "DUQ": (40.45, -79.95), "EKPC": (38.20, -84.90),
    "JCPL": (40.25, -74.25), "METED": (40.33, -76.00),
    "PECO": (40.00, -75.15), "PENELEC": (41.00, -78.50),
    "PEPCO": (38.90, -77.00), "PPL": (40.60, -76.00),
    "PSEG": (40.73, -74.17), "RECO": (41.05, -74.13),
}


def _make_session() -> requests.Session:
    """Create requests session with browser-like headers."""
    session = requests.Session()
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    })
    return session


def _fetch_with_retry(session: requests.Session, url: str, retries: int = 3) -> Optional[str]:
    """Fetch URL with exponential backoff retries."""
    for attempt in range(retries):
        try:
            resp = session.get(url, timeout=30)
            resp.raise_for_status()
            return resp.text
        except requests.RequestException as e:
            wait = 2 ** attempt
            if attempt < retries - 1:
                logger.warning(f"Fetch failed ({e}), retrying in {wait}s...")
                time.sleep(wait)
            else:
                logger.error(f"Failed to fetch {url} after {retries} attempts: {e}")
    return None


# ── Scraping functions ──


def scrape_state_listings(states: Optional[list] = None, force: bool = False) -> list:
    """
    Scrape data center listings from state pages.

    Each state page has an HTML table with facility name, county, status,
    capacity, and a link to the detail page.

    Returns list of dicts with keys: facility_name, county, state, state_code,
    status, capacity, detail_slug.
    """
    if states is None:
        states = PJM_STATES

    if DC_LISTINGS_CACHE.exists() and not force:
        with open(DC_LISTINGS_CACHE) as f:
            cached = json.load(f)
        logger.info(f"Loaded {len(cached)} cached DC state listings")
        return cached

    session = _make_session()
    listings = []

    for state_code in states:
        url = f"{BASE_URL}/data-center/state/{state_code}"
        logger.info(f"Scraping DC listings: {state_code}")

        page_html = _fetch_with_retry(session, url)
        if not page_html:
            logger.warning(f"Skipping {state_code}: could not fetch page")
            continue

        soup = BeautifulSoup(page_html, "html.parser")

        # Find the data table
        table = soup.find("table")
        if not table:
            logger.warning(f"No table found on {state_code} page")
            continue

        rows = table.find_all("tr")
        for row in rows[1:]:  # skip header
            cells = row.find_all("td")
            if len(cells) < 3:
                continue

            # Extract detail slug from link
            link = cells[0].find("a")
            detail_slug = ""
            facility_name = cells[0].get_text(strip=True)
            if link and link.get("href"):
                href = link["href"]
                # href format: /data-center/project/{slug}
                parts = href.rstrip("/").split("/")
                detail_slug = parts[-1] if parts else ""
                facility_name = link.get_text(strip=True)

            county = cells[1].get_text(strip=True) if len(cells) > 1 else ""
            status = cells[2].get_text(strip=True) if len(cells) > 2 else ""
            capacity = cells[3].get_text(strip=True) if len(cells) > 3 else ""

            listings.append({
                "facility_name": facility_name,
                "county": county,
                "state_code": state_code,
                "status": status,
                "capacity": capacity,
                "detail_slug": detail_slug,
            })

        time.sleep(1.0)

    # Cache results
    DC_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with open(DC_LISTINGS_CACHE, "w") as f:
        json.dump(listings, f, indent=2)
    logger.info(f"Scraped {len(listings)} DC listings from {len(states)} states")

    return listings


def scrape_detail_pages(listings: list, force: bool = False) -> dict:
    """
    Scrape detail pages for each listing to get address, grid operator, etc.

    Incremental: caches by slug, skips already-cached entries on restart.
    Flushes to disk every 50 records.

    Returns dict keyed by slug with detail fields.
    """
    # Load existing cache
    details = {}
    if DC_DETAILS_CACHE.exists() and not force:
        with open(DC_DETAILS_CACHE) as f:
            details = json.load(f)
        logger.info(f"Loaded {len(details)} cached DC detail pages")

    # Find slugs we still need
    all_slugs = [l["detail_slug"] for l in listings if l.get("detail_slug")]
    to_scrape = [s for s in all_slugs if s not in details]

    if not to_scrape:
        logger.info("All DC detail pages already cached")
        return details

    logger.info(f"DC details: {len(all_slugs)} total, {len(details)} cached, {len(to_scrape)} to scrape")

    session = _make_session()
    scraped_count = 0

    for i, slug in enumerate(to_scrape):
        url = f"{BASE_URL}/data-center/project/{slug}"

        page_html = _fetch_with_retry(session, url)
        if not page_html:
            details[slug] = {"error": "fetch_failed"}
            scraped_count += 1
            continue

        soup = BeautifulSoup(page_html, "html.parser")
        detail = _parse_detail_page(soup)
        details[slug] = detail
        scraped_count += 1

        # Progress logging
        if (i + 1) % 50 == 0:
            logger.info(f"  Scraped {i + 1}/{len(to_scrape)} detail pages...")
            # Incremental flush
            DC_CACHE_DIR.mkdir(parents=True, exist_ok=True)
            with open(DC_DETAILS_CACHE, "w") as f:
                json.dump(details, f, indent=2)

        time.sleep(0.5)

    # Final save
    DC_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with open(DC_DETAILS_CACHE, "w") as f:
        json.dump(details, f, indent=2)
    logger.info(f"Scraped {scraped_count} DC detail pages")

    return details


def _parse_detail_page(soup: BeautifulSoup) -> dict:
    """Extract structured fields from a detail page."""
    detail = {
        "address": "",
        "city": "",
        "zip": "",
        "grid_operator": "",
        "operator": "",
        "dates": "",
    }

    # Detail pages typically have definition list or table-like structures
    # Try multiple selectors to be robust

    # Look for dl/dt/dd pairs
    for dt in soup.find_all("dt"):
        label = dt.get_text(strip=True).lower()
        dd = dt.find_next_sibling("dd")
        if not dd:
            continue
        value = dd.get_text(strip=True)
        _assign_detail_field(detail, label, value)

    # Also try table rows (some pages use tables)
    for row in soup.find_all("tr"):
        cells = row.find_all(["th", "td"])
        if len(cells) >= 2:
            label = cells[0].get_text(strip=True).lower()
            value = cells[1].get_text(strip=True)
            _assign_detail_field(detail, label, value)

    # Try key-value divs (class patterns like "detail-item", "info-row", etc.)
    for div in soup.find_all("div", class_=re.compile(r"detail|info|field|property", re.I)):
        label_el = div.find(["span", "strong", "b", "label"])
        if label_el:
            label = label_el.get_text(strip=True).lower().rstrip(":")
            # Get remaining text after the label element
            value = div.get_text(strip=True).replace(label_el.get_text(strip=True), "").strip().lstrip(":")
            if value:
                _assign_detail_field(detail, label, value)

    # Clean up gated/sales CTA strings from protected fields
    for key in detail:
        if isinstance(detail[key], str) and "contact sales" in detail[key].lower():
            detail[key] = ""

    return detail


def _assign_detail_field(detail: dict, label: str, value: str):
    """Assign a value to the appropriate detail field based on label text."""
    label = label.rstrip(":").strip()
    if any(k in label for k in ("address", "street", "location")):
        if not detail["address"]:
            detail["address"] = value
    elif "city" in label:
        detail["city"] = value
    elif "zip" in label or "postal" in label:
        detail["zip"] = value
    elif "grid" in label or "utility" in label or "electric provider" in label:
        detail["grid_operator"] = value
    elif "operator" in label or "owner" in label or "developer" in label:
        if not detail["operator"]:
            detail["operator"] = value
    elif "date" in label or "year" in label or "commissioned" in label:
        detail["dates"] = value


# ── Zone mapping ──


def map_grid_operator_to_zone(grid_operator: str) -> Optional[str]:
    """
    Map a grid operator string to a PJM zone code.

    1. Exact match (lowercased) against GRID_OPERATOR_TO_ZONE
    2. Substring fallback against _OPERATOR_SUBSTRING_MAP
    3. Returns None for non-PJM operators or unrecognized strings
    """
    if not grid_operator:
        return None

    normalized = grid_operator.strip().lower()

    # Exact match
    zone = GRID_OPERATOR_TO_ZONE.get(normalized)
    if zone is not None:
        return zone  # zone could be None for non-PJM operators
    if normalized in GRID_OPERATOR_TO_ZONE:
        return None  # explicitly non-PJM

    # Substring fallback
    for keyword, zone_code in _OPERATOR_SUBSTRING_MAP.items():
        if keyword in normalized:
            return zone_code

    logger.warning(f"Unmapped grid operator: '{grid_operator}'")
    return None


def _parse_capacity_mw(capacity_str: str) -> float:
    """Parse capacity range string to MW midpoint estimate."""
    if not capacity_str:
        return 0.0
    normalized = capacity_str.strip().lower()
    for pattern, midpoint in CAPACITY_MIDPOINTS.items():
        if pattern in normalized or normalized in pattern:
            return float(midpoint)
    # Try to extract a number
    nums = re.findall(r"[\d.]+", capacity_str)
    if nums:
        return float(nums[0])
    return 0.0


# ── Data combination ──


def combine_dc_data(listings: list, details: dict) -> list:
    """
    Merge listing + detail data by slug. Apply zone mapping and capacity parsing.
    Filter to PJM-only records (zone != None).
    """
    records = []
    unmapped_count = 0

    for listing in listings:
        slug = listing.get("detail_slug", "")
        detail = details.get(slug, {})

        if detail.get("error"):
            detail = {}

        grid_operator = detail.get("grid_operator", "")
        pjm_zone = map_grid_operator_to_zone(grid_operator)

        capacity_mw = _parse_capacity_mw(listing.get("capacity", ""))
        status = listing.get("status", "").strip().lower()

        # Normalize status
        if "operational" in status or "operating" in status:
            status_norm = "operational"
        elif "proposed" in status or "planned" in status:
            status_norm = "proposed"
        elif "construction" in status or "building" in status:
            status_norm = "construction"
        else:
            status_norm = status or "unknown"

        record = {
            "slug": slug,
            "facility_name": listing.get("facility_name", ""),
            "county": listing.get("county", ""),
            "state_code": listing.get("state_code", ""),
            "status": status_norm,
            "capacity": listing.get("capacity", ""),
            "capacity_mw": capacity_mw,
            "address": detail.get("address", ""),
            "city": detail.get("city", ""),
            "zip": detail.get("zip", ""),
            "grid_operator": grid_operator,
            "operator": detail.get("operator", ""),
            "pjm_zone": pjm_zone,
        }

        if pjm_zone:
            records.append(record)
        else:
            unmapped_count += 1

    # Cache combined data
    DC_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with open(DC_COMBINED_CACHE, "w") as f:
        json.dump(records, f, indent=2)

    logger.info(
        f"Combined DC data: {len(records)} PJM records, "
        f"{unmapped_count} filtered (non-PJM/unmapped)"
    )
    return records


# ── Geocoding ──


def geocode_dc_addresses(dc_records: list, force: bool = False) -> dict:
    """
    Geocode data center addresses using Nominatim.

    Same pattern as geocode_pnodes() in data_acquisition.py:
    - address+city+state+zip for primary query
    - Falls back to county+state, then zone centroid
    - 1 req/sec rate limit
    - Incremental caching to data/geo/dc_coordinates.json
    """
    # Load existing cache
    cache = {}
    if DC_COORDINATES_CACHE.exists() and not force:
        with open(DC_COORDINATES_CACHE) as f:
            cache = json.load(f)
        logger.info(f"Loaded {len(cache)} cached DC coordinates")

    # Find records not yet cached
    to_geocode = [r for r in dc_records if r["slug"] not in cache]
    logger.info(
        f"DC geocoding: {len(dc_records)} records, "
        f"{len(cache)} cached, {len(to_geocode)} to geocode"
    )

    if not to_geocode:
        return cache

    session = requests.Session()
    session.headers.update({
        "User-Agent": "grid-constraint-classifier/1.0 (data center geocoding)",
    })

    geocoded = 0
    fallback = 0

    for i, record in enumerate(to_geocode):
        slug = record["slug"]
        result = None

        # Try full address
        addr = record.get("address", "")
        city = record.get("city", "")
        state_code = record.get("state_code", "")
        zipcode = record.get("zip", "")

        if addr:
            query = f"{addr}, {city}, {state_code} {zipcode}".strip().strip(",")
            result = _geocode_nominatim(session, query)

        # Fallback: county + state
        if not result:
            county = record.get("county", "")
            if county:
                query = f"{county} County, {state_code}"
                result = _geocode_nominatim(session, query)

        if result:
            cache[slug] = {
                "lat": result[0],
                "lon": result[1],
                "source": "nominatim",
            }
            geocoded += 1
        else:
            # Fall back to jittered zone centroid
            zone = record.get("pjm_zone", "")
            centroid = _ZONE_CENTROIDS.get(zone, (39.5, -78.0))
            cache[slug] = {
                "lat": centroid[0] + random.uniform(-0.15, 0.15),
                "lon": centroid[1] + random.uniform(-0.15, 0.15),
                "source": "zone_centroid",
            }
            fallback += 1

        if (i + 1) % 50 == 0:
            logger.info(f"  Geocoded {i + 1}/{len(to_geocode)} DCs...")
            # Incremental save
            GEO_CACHE_DIR.mkdir(parents=True, exist_ok=True)
            with open(DC_COORDINATES_CACHE, "w") as f:
                json.dump(cache, f, indent=2)

        time.sleep(1.0)

    logger.info(f"DC geocoding complete: {geocoded} matched, {fallback} fell back to zone centroid")

    # Save final cache
    GEO_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with open(DC_COORDINATES_CACHE, "w") as f:
        json.dump(cache, f, indent=2)
    logger.info(f"Saved {len(cache)} DC coordinates to {DC_COORDINATES_CACHE}")

    return cache


def _geocode_nominatim(session: requests.Session, query: str) -> Optional[tuple]:
    """Single Nominatim geocode request. Returns (lat, lon) or None."""
    try:
        resp = session.get(
            "https://nominatim.openstreetmap.org/search",
            params={
                "q": query,
                "format": "json",
                "limit": 1,
                "countrycodes": "us",
            },
            timeout=10,
        )
        resp.raise_for_status()
        results = resp.json()
        if results:
            return (float(results[0]["lat"]), float(results[0]["lon"]))
    except Exception as e:
        logger.debug(f"Geocode failed for '{query}': {e}")
    return None


# ── Summary / aggregation ──


def build_dc_summary(dc_records: list) -> dict:
    """
    Aggregate data center records by zone.

    Returns structured dict with:
    - totals: count, estimated_mw, by status
    - by_zone: per-zone breakdown with count, status counts, estimated_mw,
      top_counties, top_operators
    """
    if not dc_records:
        return {}

    by_zone = {}
    total_mw = 0.0
    status_totals = {"operational": 0, "proposed": 0, "construction": 0, "unknown": 0}

    for rec in dc_records:
        zone = rec.get("pjm_zone", "UNKNOWN")
        status = rec.get("status", "unknown")
        mw = rec.get("capacity_mw", 0.0)

        if zone not in by_zone:
            by_zone[zone] = {
                "total": 0,
                "operational": 0,
                "proposed": 0,
                "construction": 0,
                "unknown": 0,
                "estimated_mw": 0.0,
                "counties": {},
                "operators": {},
            }

        entry = by_zone[zone]
        entry["total"] += 1
        entry[status] = entry.get(status, 0) + 1
        entry["estimated_mw"] += mw

        county = rec.get("county", "")
        if county:
            entry["counties"][county] = entry["counties"].get(county, 0) + 1

        operator = rec.get("operator", "")
        if operator:
            entry["operators"][operator] = entry["operators"].get(operator, 0) + 1

        total_mw += mw
        status_totals[status] = status_totals.get(status, 0) + 1

    # Build per-zone summary with top counties/operators
    zone_summaries = {}
    for zone, data in sorted(by_zone.items()):
        top_counties = sorted(data["counties"].items(), key=lambda x: -x[1])[:5]
        top_operators = sorted(data["operators"].items(), key=lambda x: -x[1])[:5]

        zone_summaries[zone] = {
            "total": data["total"],
            "operational": data["operational"],
            "proposed": data["proposed"],
            "construction": data["construction"],
            "estimated_mw": round(data["estimated_mw"], 1),
            "top_counties": [{"name": c, "count": n} for c, n in top_counties],
            "top_operators": [{"name": o, "count": n} for o, n in top_operators],
        }

    return {
        "total_count": len(dc_records),
        "total_estimated_mw": round(total_mw, 1),
        "status_totals": status_totals,
        "by_zone": zone_summaries,
    }


# ── Convenience loader ──


def load_dc_data() -> tuple:
    """
    Load cached DC data and coordinates.

    Returns (dc_records, dc_coordinates) or ([], {}) if no cache exists.
    """
    dc_records = []
    dc_coordinates = {}

    if DC_COMBINED_CACHE.exists():
        with open(DC_COMBINED_CACHE) as f:
            dc_records = json.load(f)
        logger.info(f"Loaded {len(dc_records)} cached DC records")

    if DC_COORDINATES_CACHE.exists():
        with open(DC_COORDINATES_CACHE) as f:
            dc_coordinates = json.load(f)
        logger.info(f"Loaded {len(dc_coordinates)} cached DC coordinates")

    return dc_records, dc_coordinates
