"""
Exelon hosting capacity adapter.

Handles the 6 Exelon utilities (ComEd, PECO, BGE, Pepco, DPL, ACE)
that share ArcGIS org agWTKEK7X5K1Bx7o. Extends the generic ArcGIS
adapter with support for ComEd's quarterly URL rotation.
"""

import logging
from datetime import datetime

from .arcgis_adapter import ArcGISHostingCapacityAdapter

logger = logging.getLogger(__name__)

# Exelon shared ArcGIS org catalog
EXELON_CATALOG_URL = (
    "https://services3.arcgis.com/agWTKEK7X5K1Bx7o/arcgis/rest/services"
)

# Quarter month abbreviations for URL patterns
QUARTER_MONTHS = {
    1: "MAR", 2: "MAR", 3: "MAR",
    4: "JUN", 5: "JUN", 6: "JUN",
    7: "SEP", 8: "SEP", 9: "SEP",
    10: "DEC", 11: "DEC", 12: "DEC",
}

# Fallback order: try current quarter, then go backwards
QUARTER_ORDER = ["MAR", "JUN", "SEP", "DEC"]


class ExelonHostingCapacityAdapter(ArcGISHostingCapacityAdapter):
    """Adapter for Exelon utilities with quarterly URL rotation support."""

    def resolve_current_url(self) -> str:
        """Resolve the current service URL, handling quarterly rotation."""
        if self.config.url_discovery_method == "quarterly_name":
            return self._resolve_quarterly_url()
        return super().resolve_current_url()

    def _resolve_quarterly_url(self) -> str:
        """Find the current quarterly service by scanning the catalog.

        ComEd publishes services named like:
          ComEd_PV_Hosting_Capacity_MAR2026
          ComEd_PV_Hosting_Capacity_DEC2025

        Tries current quarter first, then falls back to previous quarters.
        """
        if not self.config.url_pattern:
            raise ValueError(
                f"{self.config.utility_code}: url_pattern required for "
                "quarterly_name discovery"
            )

        # Discover available services
        services = self.client.discover_layers(EXELON_CATALOG_URL)
        service_names = {s["name"] for s in services}

        now = datetime.now()
        year = now.year
        current_quarter_month = QUARTER_MONTHS[now.month]

        # Build candidate list: current quarter back through 4 quarters
        candidates = []
        start_idx = QUARTER_ORDER.index(current_quarter_month)
        check_year = year
        for i in range(5):  # check up to 5 quarters back
            idx = (start_idx - i) % 4
            month_abbr = QUARTER_ORDER[idx]
            if i > 0 and idx == 3:  # wrapped to DEC, go back a year
                check_year -= 1
            candidate = self.config.url_pattern.format(
                month=month_abbr, year=check_year,
            )
            candidates.append(candidate)

        # Find the first matching service
        for candidate in candidates:
            if candidate in service_names:
                url = f"{EXELON_CATALOG_URL}/{candidate}/FeatureServer"
                layer_idx = self.config.layer_index or 0
                logger.info(
                    f"Resolved quarterly URL for {self.config.utility_code}: "
                    f"{candidate}"
                )
                return f"{url}/{layer_idx}/query"

        # Fallback to static config
        logger.warning(
            f"No quarterly service found for {self.config.utility_code}, "
            f"tried: {candidates}. Falling back to static URL."
        )
        return super().resolve_current_url()
