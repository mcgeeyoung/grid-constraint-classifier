"""
Xcel Energy hosting capacity adapter.

Handles Xcel's two operating companies (NSPM = Minnesota, PSCO = Colorado)
that publish hosting capacity data on ArcGIS org eM84fwjsSggLQk61 with
monthly URL rotation patterns.

Service naming patterns observed:
  MN: NSP_HCA_Popup_Layer_March_2026, HCA_NSP_Popup_Layer_February_2026,
      NSP_HCA_Popup_Nov2025, HCA_NSP_Popup_202509, etc.
  CO: PSCO_GEN_Popup_Layer_Feb_2026, PSCOPopUpData2024, etc.

Strategy: scan the ArcGIS catalog for services matching a prefix pattern,
sort by recency, and use the most recent one.
"""

import logging
import re
from datetime import datetime
from typing import Optional

from .arcgis_adapter import ArcGISHostingCapacityAdapter

logger = logging.getLogger(__name__)

XCEL_CATALOG_URL = (
    "https://services1.arcgis.com/eM84fwjsSggLQk61/arcgis/rest/services"
)

# Month name/abbreviation patterns for parsing service names
MONTH_NAMES = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4,
    "jun": 6, "jul": 7, "aug": 8, "sep": 9,
    "oct": 10, "nov": 11, "dec": 12,
}


def _parse_service_date(name: str) -> Optional[datetime]:
    """Try to extract a date from an Xcel service name.

    Handles patterns like:
      NSP_HCA_Popup_Layer_March_2026
      HCA_NSP_Popup_Layer_February_2026
      NSP_HCA_Popup_Nov2025
      HCA_NSP_Popup_202509
      PSCO_GEN_Popup_Layer_Feb_2026
    """
    name_lower = name.lower()

    # Pattern 1: month_year (e.g. march_2026, feb_2026)
    for month_str, month_num in MONTH_NAMES.items():
        match = re.search(rf"{month_str}[_]?(\d{{4}})", name_lower)
        if match:
            year = int(match.group(1))
            return datetime(year, month_num, 1)

    # Pattern 2: year+month digits (e.g. 202509)
    match = re.search(r"(\d{4})(\d{2})", name_lower)
    if match:
        year, month = int(match.group(1)), int(match.group(2))
        if 2020 <= year <= 2030 and 1 <= month <= 12:
            return datetime(year, month, 1)

    return None


class XcelHostingCapacityAdapter(ArcGISHostingCapacityAdapter):
    """Adapter for Xcel Energy utilities with monthly URL rotation."""

    def resolve_current_url(self) -> str:
        """Resolve the current service URL by scanning the catalog."""
        if self.config.url_discovery_method == "catalog_scan":
            return self._resolve_latest_url()
        return super().resolve_current_url()

    def _resolve_latest_url(self) -> str:
        """Find the most recent service by scanning the Xcel ArcGIS catalog.

        Filters services matching the url_pattern prefix, parses dates from
        service names, and returns the most recent one.
        """
        prefix = self.config.url_pattern
        if not prefix:
            raise ValueError(
                f"{self.config.utility_code}: url_pattern (prefix) required "
                "for catalog_scan discovery"
            )

        # Discover all services
        services = self.client.discover_layers(XCEL_CATALOG_URL)
        service_names = [s["name"] for s in services]

        # Filter by prefix pattern
        prefix_lower = prefix.lower()
        candidates = []
        for name in service_names:
            if prefix_lower in name.lower():
                dt = _parse_service_date(name)
                if dt:
                    candidates.append((dt, name))

        if not candidates:
            logger.warning(
                f"No services matching '{prefix}' found for "
                f"{self.config.utility_code}. Falling back to static URL."
            )
            return super().resolve_current_url()

        # Sort by date descending, pick the most recent
        candidates.sort(key=lambda x: x[0], reverse=True)
        best_dt, best_name = candidates[0]

        url = f"{XCEL_CATALOG_URL}/{best_name}/FeatureServer"
        layer_idx = self.config.layer_index or 0
        logger.info(
            f"Resolved latest Xcel service for {self.config.utility_code}: "
            f"{best_name} ({best_dt.strftime('%Y-%m')})"
        )
        return f"{url}/{layer_idx}/query"
