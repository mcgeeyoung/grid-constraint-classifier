"""
Multi-ISO data center scraper for interconnection.fyi.

Accepts ISO-specific configuration (states, operator-to-zone mapping)
to scrape and classify data centers across any ISO footprint.

The core scraping logic from the original PJM scraper is preserved;
this module wraps it to accept per-ISO config from YAML files.
"""

import json
import logging
import re
import random
import time
from pathlib import Path
from typing import Optional

import requests
import yaml
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

BASE_URL = "https://www.interconnection.fyi"

# Capacity range strings -> MW midpoint estimates
CAPACITY_MIDPOINTS = {
    "< 10 mw": 5, "<10 mw": 5,
    "10-25 mw": 17, "10 - 25 mw": 17,
    "25-50 mw": 37, "25 - 50 mw": 37,
    "10-50 mw": 30, "10 - 50 mw": 30,
    "50-100 mw": 75, "50 - 100 mw": 75,
    "100-250 mw": 175, "100 - 250 mw": 175,
    "250+ mw": 375, "250 + mw": 375,
    ">250 mw": 375, "unknown": 0, "": 0,
}

CONFIGS_DIR = Path(__file__).parent / "dc_configs"


def load_dc_config(iso_id: str) -> dict:
    """
    Load DC scraper config for an ISO.

    Config includes:
      - states: list of state codes to scrape
      - operator_to_zone: {operator_string: zone_code} mapping
      - operator_substring_map: {keyword: zone_code} for fallback matching
      - zone_centroids: {zone: (lat, lon)} for geocoding fallback
    """
    config_path = CONFIGS_DIR / f"{iso_id}.yaml"
    if not config_path.exists():
        logger.warning(f"No DC config for {iso_id} at {config_path}")
        return {"states": [], "operator_to_zone": {}, "operator_substring_map": {}}

    with open(config_path) as f:
        return yaml.safe_load(f)


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


def scrape_state_listings(
    states: list[str],
    cache_path: Path,
    force: bool = False,
) -> list:
    """
    Scrape data center listings from state pages.

    Args:
        states: List of state codes to scrape (e.g. ["VA", "OH"])
        cache_path: Path to cache the listings JSON
        force: Force re-scrape

    Returns:
        List of listing dicts.
    """
    if cache_path.exists() and not force:
        with open(cache_path) as f:
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
            continue

        soup = BeautifulSoup(page_html, "html.parser")
        table = soup.find("table")
        if not table:
            logger.warning(f"No table found on {state_code} page")
            continue

        rows = table.find_all("tr")
        for row in rows[1:]:
            cells = row.find_all("td")
            if len(cells) < 3:
                continue

            link = cells[0].find("a")
            detail_slug = ""
            facility_name = cells[0].get_text(strip=True)
            if link and link.get("href"):
                parts = link["href"].rstrip("/").split("/")
                detail_slug = parts[-1] if parts else ""
                facility_name = link.get_text(strip=True)

            listings.append({
                "facility_name": facility_name,
                "county": cells[1].get_text(strip=True) if len(cells) > 1 else "",
                "state_code": state_code,
                "status": cells[2].get_text(strip=True) if len(cells) > 2 else "",
                "capacity": cells[3].get_text(strip=True) if len(cells) > 3 else "",
                "detail_slug": detail_slug,
            })

        time.sleep(1.0)

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    with open(cache_path, "w") as f:
        json.dump(listings, f, indent=2)
    logger.info(f"Scraped {len(listings)} DC listings from {len(states)} states")

    return listings


def scrape_detail_pages(
    listings: list,
    cache_path: Path,
    force: bool = False,
) -> dict:
    """
    Scrape detail pages for each listing.

    Returns dict keyed by slug with detail fields.
    """
    details = {}
    if cache_path.exists() and not force:
        with open(cache_path) as f:
            details = json.load(f)
        logger.info(f"Loaded {len(details)} cached DC detail pages")

    all_slugs = [l["detail_slug"] for l in listings if l.get("detail_slug")]
    to_scrape = [s for s in all_slugs if s not in details]

    if not to_scrape:
        logger.info("All DC detail pages already cached")
        return details

    logger.info(f"DC details: {len(all_slugs)} total, {len(details)} cached, {len(to_scrape)} to scrape")

    session = _make_session()

    for i, slug in enumerate(to_scrape):
        url = f"{BASE_URL}/data-center/project/{slug}"
        page_html = _fetch_with_retry(session, url)
        if not page_html:
            details[slug] = {"error": "fetch_failed"}
            continue

        soup = BeautifulSoup(page_html, "html.parser")
        details[slug] = _parse_detail_page(soup)

        if (i + 1) % 50 == 0:
            logger.info(f"  Scraped {i + 1}/{len(to_scrape)} detail pages...")
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            with open(cache_path, "w") as f:
                json.dump(details, f, indent=2)

        time.sleep(0.5)

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    with open(cache_path, "w") as f:
        json.dump(details, f, indent=2)

    return details


def _parse_detail_page(soup: BeautifulSoup) -> dict:
    """Extract structured fields from a detail page."""
    detail = {
        "address": "", "city": "", "zip": "",
        "grid_operator": "", "operator": "", "dates": "",
    }

    for dt in soup.find_all("dt"):
        label = dt.get_text(strip=True).lower()
        dd = dt.find_next_sibling("dd")
        if dd:
            _assign_detail_field(detail, label, dd.get_text(strip=True))

    for row in soup.find_all("tr"):
        cells = row.find_all(["th", "td"])
        if len(cells) >= 2:
            _assign_detail_field(
                detail,
                cells[0].get_text(strip=True).lower(),
                cells[1].get_text(strip=True),
            )

    for div in soup.find_all("div", class_=re.compile(r"detail|info|field|property", re.I)):
        label_el = div.find(["span", "strong", "b", "label"])
        if label_el:
            label = label_el.get_text(strip=True).lower().rstrip(":")
            value = div.get_text(strip=True).replace(
                label_el.get_text(strip=True), ""
            ).strip().lstrip(":")
            if value:
                _assign_detail_field(detail, label, value)

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


def map_operator_to_zone(
    grid_operator: str,
    operator_to_zone: dict,
    operator_substring_map: dict,
) -> Optional[str]:
    """
    Map a grid operator string to a zone code using the provided mappings.

    1. Exact match (lowercased)
    2. Substring fallback
    3. Returns None for unmapped
    """
    if not grid_operator:
        return None

    normalized = grid_operator.strip().lower()

    zone = operator_to_zone.get(normalized)
    if zone is not None:
        return zone
    if normalized in operator_to_zone:
        return None

    for keyword, zone_code in operator_substring_map.items():
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
    nums = re.findall(r"[\d.]+", capacity_str)
    if nums:
        return float(nums[0])
    return 0.0


def combine_dc_data(
    listings: list,
    details: dict,
    operator_to_zone: dict,
    operator_substring_map: dict,
    cache_path: Path,
) -> list:
    """
    Merge listing + detail data, apply zone mapping, filter to ISO records.
    """
    records = []
    unmapped_count = 0

    for listing in listings:
        slug = listing.get("detail_slug", "")
        detail = details.get(slug, {})
        if detail.get("error"):
            detail = {}

        grid_operator = detail.get("grid_operator", "")
        zone = map_operator_to_zone(
            grid_operator, operator_to_zone, operator_substring_map
        )

        capacity_mw = _parse_capacity_mw(listing.get("capacity", ""))
        status = listing.get("status", "").strip().lower()

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
            "iso_zone": zone,
        }

        if zone:
            records.append(record)
        else:
            unmapped_count += 1

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    with open(cache_path, "w") as f:
        json.dump(records, f, indent=2)

    logger.info(
        f"Combined DC data: {len(records)} ISO records, "
        f"{unmapped_count} filtered (unmapped)"
    )
    return records


def build_dc_summary(dc_records: list, zone_key: str = "iso_zone") -> dict:
    """
    Aggregate data center records by zone.

    Returns structured dict with totals and per-zone breakdown.
    """
    if not dc_records:
        return {}

    by_zone = {}
    total_mw = 0.0
    status_totals = {"operational": 0, "proposed": 0, "construction": 0, "unknown": 0}

    for rec in dc_records:
        zone = rec.get(zone_key, "UNKNOWN")
        status = rec.get("status", "unknown")
        mw = rec.get("capacity_mw", 0.0)

        if zone not in by_zone:
            by_zone[zone] = {
                "total": 0, "operational": 0, "proposed": 0,
                "construction": 0, "unknown": 0,
                "estimated_mw": 0.0, "counties": {}, "operators": {},
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
