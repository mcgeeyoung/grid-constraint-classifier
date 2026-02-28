"""ISO/RTO planning data source registry and downloaders.

Each ISO/RTO publishes planning documents and structured data:
  - CAISO: Transmission Plan, local capacity requirements
  - PJM: Regional Transmission Expansion Plan, load forecast
  - ERCOT: Long-term system assessment, CDR reports
  - NYISO: Gold Book (load forecast), RNA, CARIS
  - ISO-NE: Regional System Plan, Forward Capacity Market data
  - MISO: MTEP (transmission plan), resource adequacy
  - SPP: ITP studies, generation interconnection queue

This module provides a registry of data sources and download helpers
for each ISO/RTO's publicly available planning data.
"""

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
from pathlib import Path

import requests

logger = logging.getLogger(__name__)


class ISOCode(str, Enum):
    CAISO = "CAISO"
    PJM = "PJM"
    ERCOT = "ERCOT"
    NYISO = "NYISO"
    ISONE = "ISO-NE"
    MISO = "MISO"
    SPP = "SPP"


@dataclass
class PlanningDataSource:
    """A planning data source published by an ISO/RTO."""
    iso_code: str
    name: str
    description: str
    url: str
    data_type: str  # report, dataset, api, portal
    format: str  # pdf, xlsx, csv, json, html
    frequency: str  # annual, quarterly, monthly, ad-hoc
    categories: list[str] = field(default_factory=list)
    notes: Optional[str] = None


# Registry of all known ISO/RTO planning data sources
ISO_PLANNING_SOURCES: list[PlanningDataSource] = [
    # === CAISO ===
    PlanningDataSource(
        iso_code="CAISO",
        name="CAISO Transmission Plan",
        description="Annual transmission planning process results including reliability, "
                    "policy-driven, and economic assessments.",
        url="https://www.caiso.com/planning/Pages/TransmissionPlanning/Default.aspx",
        data_type="report",
        format="pdf",
        frequency="annual",
        categories=["transmission_plan", "grid_constraint", "resource_need"],
    ),
    PlanningDataSource(
        iso_code="CAISO",
        name="CAISO Local Capacity Requirements",
        description="Annual local capacity technical study identifying minimum capacity "
                    "needs in local reliability areas.",
        url="https://www.caiso.com/planning/Pages/ReliabilityRequirements/Default.aspx",
        data_type="report",
        format="pdf",
        frequency="annual",
        categories=["grid_constraint", "resource_need"],
    ),
    PlanningDataSource(
        iso_code="CAISO",
        name="CAISO Generator Interconnection Queue",
        description="Active queue of generation interconnection requests.",
        url="https://www.caiso.com/planning/Pages/GeneratorInterconnection/Default.aspx",
        data_type="dataset",
        format="xlsx",
        frequency="monthly",
        categories=["interconnection_queue"],
    ),
    PlanningDataSource(
        iso_code="CAISO",
        name="CAISO Demand Forecast",
        description="California Energy Demand forecast used for planning.",
        url="https://www.caiso.com/planning/Pages/ReliabilityRequirements/Default.aspx",
        data_type="dataset",
        format="xlsx",
        frequency="annual",
        categories=["load_forecast"],
    ),
    # === PJM ===
    PlanningDataSource(
        iso_code="PJM",
        name="PJM Regional Transmission Expansion Plan (RTEP)",
        description="Annual plan identifying transmission reinforcements needed for "
                    "reliability and economic efficiency across PJM footprint.",
        url="https://www.pjm.com/planning/rtep-development",
        data_type="report",
        format="pdf",
        frequency="annual",
        categories=["transmission_plan", "grid_constraint"],
    ),
    PlanningDataSource(
        iso_code="PJM",
        name="PJM Load Forecast",
        description="Long-term load forecast by zone for capacity planning.",
        url="https://www.pjm.com/planning/resource-adequacy-planning/load-forecast",
        data_type="dataset",
        format="xlsx",
        frequency="annual",
        categories=["load_forecast"],
    ),
    PlanningDataSource(
        iso_code="PJM",
        name="PJM New Services Queue",
        description="Generation and transmission interconnection queue.",
        url="https://www.pjm.com/planning/services-requests/interconnection-queues",
        data_type="dataset",
        format="xlsx",
        frequency="monthly",
        categories=["interconnection_queue"],
    ),
    PlanningDataSource(
        iso_code="PJM",
        name="PJM Reliability Pricing Model (RPM)",
        description="Capacity market auction results with locational constraints.",
        url="https://www.pjm.com/markets-and-operations/rpm",
        data_type="dataset",
        format="xlsx",
        frequency="annual",
        categories=["resource_need"],
    ),
    # === ERCOT ===
    PlanningDataSource(
        iso_code="ERCOT",
        name="ERCOT Long-Term System Assessment",
        description="Multi-year assessment of ERCOT system reliability and resource adequacy.",
        url="https://www.ercot.com/gridinfo/resource",
        data_type="report",
        format="pdf",
        frequency="annual",
        categories=["load_forecast", "resource_need"],
    ),
    PlanningDataSource(
        iso_code="ERCOT",
        name="ERCOT Capacity, Demand, and Reserves (CDR)",
        description="Semi-annual report on capacity, demand, and reserve margins.",
        url="https://www.ercot.com/gridinfo/resource",
        data_type="report",
        format="pdf",
        frequency="semi-annual",
        categories=["load_forecast", "resource_need"],
    ),
    PlanningDataSource(
        iso_code="ERCOT",
        name="ERCOT Generator Interconnection Status",
        description="Queue of generator interconnection requests in ERCOT.",
        url="https://www.ercot.com/gridinfo/resource",
        data_type="dataset",
        format="xlsx",
        frequency="monthly",
        categories=["interconnection_queue"],
    ),
    PlanningDataSource(
        iso_code="ERCOT",
        name="ERCOT Regional Transmission Plan",
        description="Regional planning studies identifying transmission needs.",
        url="https://www.ercot.com/gridinfo/planning",
        data_type="report",
        format="pdf",
        frequency="annual",
        categories=["transmission_plan", "grid_constraint"],
    ),
    # === NYISO ===
    PlanningDataSource(
        iso_code="NYISO",
        name="NYISO Gold Book (Load & Capacity Data)",
        description="Annual load forecast and installed capacity data for all NY zones.",
        url="https://www.nyiso.com/gold-book-resources",
        data_type="dataset",
        format="xlsx",
        frequency="annual",
        categories=["load_forecast"],
    ),
    PlanningDataSource(
        iso_code="NYISO",
        name="NYISO Reliability Needs Assessment (RNA)",
        description="Assessment of reliability needs across NYISO system.",
        url="https://www.nyiso.com/planning-studies",
        data_type="report",
        format="pdf",
        frequency="biennial",
        categories=["grid_constraint", "resource_need"],
    ),
    PlanningDataSource(
        iso_code="NYISO",
        name="NYISO CARIS (Congestion Assessment)",
        description="Congestion Assessment and Resource Integration Study "
                    "identifying congested interfaces.",
        url="https://www.nyiso.com/planning-studies",
        data_type="report",
        format="pdf",
        frequency="biennial",
        categories=["grid_constraint"],
    ),
    PlanningDataSource(
        iso_code="NYISO",
        name="NYISO Interconnection Queue",
        description="Generator interconnection queue for NYISO.",
        url="https://www.nyiso.com/interconnections",
        data_type="dataset",
        format="xlsx",
        frequency="monthly",
        categories=["interconnection_queue"],
    ),
    # === ISO-NE ===
    PlanningDataSource(
        iso_code="ISO-NE",
        name="ISO-NE Regional System Plan (RSP)",
        description="Biennial plan identifying transmission needs across New England.",
        url="https://www.iso-ne.com/system-planning/system-plans-studies/rsp",
        data_type="report",
        format="pdf",
        frequency="biennial",
        categories=["transmission_plan", "grid_constraint", "load_forecast"],
    ),
    PlanningDataSource(
        iso_code="ISO-NE",
        name="ISO-NE CELT Report",
        description="Capacity, Energy, Loads, and Transmission report. "
                    "10-year load forecast by state and zone.",
        url="https://www.iso-ne.com/system-planning/system-plans-studies/celt",
        data_type="dataset",
        format="xlsx",
        frequency="annual",
        categories=["load_forecast"],
    ),
    PlanningDataSource(
        iso_code="ISO-NE",
        name="ISO-NE Forward Capacity Market Data",
        description="Forward Capacity Auction results with locational constraints.",
        url="https://www.iso-ne.com/markets-operations/markets/forward-capacity-market",
        data_type="dataset",
        format="xlsx",
        frequency="annual",
        categories=["resource_need"],
    ),
    PlanningDataSource(
        iso_code="ISO-NE",
        name="ISO-NE Generator Interconnection Queue",
        description="Queue of interconnection requests in ISO-NE.",
        url="https://www.iso-ne.com/system-planning/interconnection-service",
        data_type="dataset",
        format="xlsx",
        frequency="monthly",
        categories=["interconnection_queue"],
    ),
    # === MISO ===
    PlanningDataSource(
        iso_code="MISO",
        name="MISO Transmission Expansion Plan (MTEP)",
        description="Annual transmission expansion plan covering 15-state MISO footprint.",
        url="https://www.misoenergy.org/planning/planning/",
        data_type="report",
        format="pdf",
        frequency="annual",
        categories=["transmission_plan", "grid_constraint"],
    ),
    PlanningDataSource(
        iso_code="MISO",
        name="MISO Resource Adequacy",
        description="Resource adequacy surveys and loss-of-load studies.",
        url="https://www.misoenergy.org/planning/resource-adequacy/",
        data_type="report",
        format="pdf",
        frequency="annual",
        categories=["resource_need", "load_forecast"],
    ),
    PlanningDataSource(
        iso_code="MISO",
        name="MISO Generator Interconnection Queue",
        description="Active generator interconnection requests in MISO.",
        url="https://www.misoenergy.org/planning/generator-interconnection/GI_Queue/",
        data_type="dataset",
        format="xlsx",
        frequency="monthly",
        categories=["interconnection_queue"],
    ),
    # === SPP ===
    PlanningDataSource(
        iso_code="SPP",
        name="SPP Integrated Transmission Plan (ITP)",
        description="Multi-year transmission planning studies for SPP region.",
        url="https://www.spp.org/engineering/transmission-planning/",
        data_type="report",
        format="pdf",
        frequency="annual",
        categories=["transmission_plan", "grid_constraint"],
    ),
    PlanningDataSource(
        iso_code="SPP",
        name="SPP Generation Interconnection Queue",
        description="Generator interconnection queue for SPP.",
        url="https://www.spp.org/engineering/generation-interconnection/",
        data_type="dataset",
        format="xlsx",
        frequency="monthly",
        categories=["interconnection_queue"],
    ),
    PlanningDataSource(
        iso_code="SPP",
        name="SPP Resource Adequacy",
        description="Resource adequacy assessments for SPP footprint.",
        url="https://www.spp.org/engineering/resource-adequacy/",
        data_type="report",
        format="pdf",
        frequency="annual",
        categories=["resource_need", "load_forecast"],
    ),
]


def get_sources_for_iso(iso_code: str) -> list[PlanningDataSource]:
    """Get all planning data sources for a given ISO/RTO."""
    return [s for s in ISO_PLANNING_SOURCES if s.iso_code == iso_code]


def get_sources_by_category(category: str) -> list[PlanningDataSource]:
    """Get all planning data sources that include a given category."""
    return [s for s in ISO_PLANNING_SOURCES if category in s.categories]


def get_sources_by_format(fmt: str) -> list[PlanningDataSource]:
    """Get all sources with a given file format (xlsx, csv, pdf, etc.)."""
    return [s for s in ISO_PLANNING_SOURCES if s.format == fmt]


def get_downloadable_datasets() -> list[PlanningDataSource]:
    """Get all sources that are structured datasets (xlsx/csv), not PDFs."""
    return [s for s in ISO_PLANNING_SOURCES if s.data_type == "dataset"]


def summarize_coverage() -> dict:
    """Summarize coverage across ISOs and categories."""
    summary = {}
    for iso_code in ISOCode:
        sources = get_sources_for_iso(iso_code.value)
        cats = set()
        for s in sources:
            cats.update(s.categories)
        summary[iso_code.value] = {
            "source_count": len(sources),
            "categories": sorted(cats),
            "has_queue": any("interconnection_queue" in s.categories for s in sources),
            "has_forecast": any("load_forecast" in s.categories for s in sources),
            "has_transmission_plan": any("transmission_plan" in s.categories for s in sources),
        }
    return summary


class ISOPlanningDownloader:
    """Generic downloader for ISO/RTO planning documents."""

    def __init__(self, rate_limit_sec: float = 2.0, timeout: int = 120):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "grid-constraint-classifier/2.0 (research)",
        })
        self.rate_limit_sec = rate_limit_sec
        self.timeout = timeout
        self._last_request = 0.0

    def download(
        self,
        url: str,
        dest_dir: Path,
        filename: Optional[str] = None,
    ) -> Optional[Path]:
        """Download a file from an ISO/RTO planning source."""
        import time

        dest_dir.mkdir(parents=True, exist_ok=True)

        if not filename:
            filename = url.split("/")[-1].split("?")[0] or "download"

        dest_path = dest_dir / filename

        if dest_path.exists():
            logger.info(f"Already downloaded: {filename}")
            return dest_path

        elapsed = time.time() - self._last_request
        if elapsed < self.rate_limit_sec:
            time.sleep(self.rate_limit_sec - elapsed)

        logger.info(f"Downloading: {url}")
        try:
            resp = self.session.get(url, timeout=self.timeout, stream=True)
            resp.raise_for_status()

            with open(dest_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)

            self._last_request = time.time()
            logger.info(f"Saved to {dest_path} ({dest_path.stat().st_size:,} bytes)")
            return dest_path

        except Exception as e:
            logger.error(f"Download failed: {e}")
            return None

    def __repr__(self) -> str:
        return "<ISOPlanningDownloader>"
