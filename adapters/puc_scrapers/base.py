"""Abstract base class for state PUC docket scrapers.

Each state PUC has a different eFiling system, but scrapers share a common
interface: search for dockets, list filings within a docket, and download
individual documents.
"""

import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Optional

import requests

logger = logging.getLogger(__name__)


@dataclass
class DocketResult:
    """A regulatory docket/proceeding returned from a search."""
    docket_number: str
    title: Optional[str] = None
    utility_name: Optional[str] = None
    filing_type: Optional[str] = None
    status: Optional[str] = None  # open, closed
    opened_date: Optional[date] = None
    source_url: Optional[str] = None


@dataclass
class FilingResult:
    """A single filing within a docket."""
    filing_id: str
    docket_number: str
    title: Optional[str] = None
    filed_date: Optional[date] = None
    filed_by: Optional[str] = None
    document_type: Optional[str] = None  # main_filing, testimony, appendix, etc.
    source_url: Optional[str] = None
    documents: list["DocumentResult"] = field(default_factory=list)


@dataclass
class DocumentResult:
    """A downloadable document (PDF, Excel, etc.) within a filing."""
    document_id: str
    filename: str
    mime_type: Optional[str] = None
    download_url: Optional[str] = None
    file_size: Optional[int] = None
    local_path: Optional[str] = None


class PUCScraper(ABC):
    """Base class for state PUC docket scrapers."""

    state: str = ""
    puc_name: str = ""
    base_url: str = ""

    def __init__(self, rate_limit_sec: float = 1.0, timeout: int = 60):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "grid-constraint-classifier/2.0 (research)",
        })
        self.rate_limit_sec = rate_limit_sec
        self.timeout = timeout
        self._last_request = 0.0

    def _rate_limited_get(self, url: str, **kwargs) -> requests.Response:
        """Make a GET request with rate limiting."""
        elapsed = time.time() - self._last_request
        if elapsed < self.rate_limit_sec:
            time.sleep(self.rate_limit_sec - elapsed)

        kwargs.setdefault("timeout", self.timeout)
        resp = self.session.get(url, **kwargs)
        self._last_request = time.time()
        resp.raise_for_status()
        return resp

    def _rate_limited_post(self, url: str, **kwargs) -> requests.Response:
        """Make a POST request with rate limiting."""
        elapsed = time.time() - self._last_request
        if elapsed < self.rate_limit_sec:
            time.sleep(self.rate_limit_sec - elapsed)

        kwargs.setdefault("timeout", self.timeout)
        resp = self.session.post(url, **kwargs)
        self._last_request = time.time()
        resp.raise_for_status()
        return resp

    @abstractmethod
    def search_dockets(
        self,
        utility_name: Optional[str] = None,
        filing_type: Optional[str] = None,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        keyword: Optional[str] = None,
    ) -> list[DocketResult]:
        """Search for dockets/proceedings matching criteria."""
        ...

    @abstractmethod
    def list_filings(self, docket_number: str) -> list[FilingResult]:
        """List all filings within a docket."""
        ...

    @abstractmethod
    def download_document(
        self,
        document: DocumentResult,
        dest_dir: Path,
    ) -> Path:
        """Download a document to local storage. Returns path to saved file."""
        ...

    def discover_active_dockets(
        self,
        filing_types: Optional[list[str]] = None,
    ) -> list[DocketResult]:
        """Discover currently active dockets of interest.

        Default implementation calls search_dockets for each filing type.
        Override for PUCs that have better discovery mechanisms.
        """
        if not filing_types:
            filing_types = ["IRP", "DRP", "GNA", "rate_case", "hosting_capacity"]

        results = []
        for ftype in filing_types:
            try:
                dockets = self.search_dockets(filing_type=ftype)
                results.extend(dockets)
                logger.info(f"  {self.state}: found {len(dockets)} {ftype} dockets")
            except Exception as e:
                logger.warning(f"  {self.state}: failed searching {ftype}: {e}")

        return results

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}(state={self.state!r})>"
