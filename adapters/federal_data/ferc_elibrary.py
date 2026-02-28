"""FERC eLibrary scraper for federal utility filings.

FERC eLibrary: https://elibrary.ferc.gov/eLibrary/search
Contains filings from all FERC-jurisdictional utilities including:
  - FERC Form 714 (annual load data for planning areas)
  - Transmission planning studies
  - Generator interconnection studies
  - Market reports from ISOs/RTOs

The eLibrary supports full-text search and filtering by:
  - Docket number (e.g., ER24-1234, EL23-5678)
  - Filing category
  - Date range
  - Accession number

Docket prefixes:
  ER = Electric Rate
  EL = Electric
  EC = Electric Corporate
  AD = Administrative
  RM = Rulemaking
  PL = Policy Statement
"""

import logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Optional

import requests

logger = logging.getLogger(__name__)

FERC_ELIBRARY_URL = "https://elibrary.ferc.gov/eLibrary"
FERC_SEARCH_URL = f"{FERC_ELIBRARY_URL}/filelist"
FERC_DOWNLOAD_URL = f"{FERC_ELIBRARY_URL}/filedownload"


@dataclass
class FERCFiling:
    """A FERC eLibrary filing result."""
    accession_number: str
    docket_number: Optional[str] = None
    description: Optional[str] = None
    filing_date: Optional[date] = None
    category: Optional[str] = None
    filer: Optional[str] = None
    documents: list[dict] = field(default_factory=list)
    source_url: Optional[str] = None


class FERCeLibraryScraper:
    """Scraper for the FERC eLibrary filing system."""

    def __init__(self, rate_limit_sec: float = 1.0, timeout: int = 60):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "grid-constraint-classifier/2.0 (research)",
        })
        self.rate_limit_sec = rate_limit_sec
        self.timeout = timeout
        self._last_request = 0.0

    def _rate_limited_get(self, url: str, **kwargs) -> requests.Response:
        """Rate-limited GET request."""
        import time
        elapsed = time.time() - self._last_request
        if elapsed < self.rate_limit_sec:
            time.sleep(self.rate_limit_sec - elapsed)
        kwargs.setdefault("timeout", self.timeout)
        resp = self.session.get(url, **kwargs)
        self._last_request = time.time()
        resp.raise_for_status()
        return resp

    def search(
        self,
        keyword: Optional[str] = None,
        docket_number: Optional[str] = None,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        category: Optional[str] = None,
        max_results: int = 50,
    ) -> list[FERCFiling]:
        """Search FERC eLibrary for filings.

        Args:
            keyword: Full-text search term.
            docket_number: FERC docket number (e.g., ER24-1234).
            date_from: Start date for filing date range.
            date_to: End date for filing date range.
            category: Filing category filter.
            max_results: Maximum results to return.
        """
        params = {
            "sort": "filing_date",
            "order": "desc",
            "max": max_results,
        }

        if keyword:
            params["textsearch"] = keyword
        if docket_number:
            params["docket"] = docket_number
        if date_from:
            params["dateFrom"] = date_from.strftime("%m/%d/%Y")
        if date_to:
            params["dateTo"] = date_to.strftime("%m/%d/%Y")
        if category:
            params["category"] = category

        logger.info(f"FERC eLibrary: searching with params={params}")

        try:
            resp = self._rate_limited_get(FERC_SEARCH_URL, params=params)

            # FERC returns HTML; try JSON if available
            content_type = resp.headers.get("content-type", "")
            if "json" in content_type:
                return self._parse_json_results(resp.json())
            return self._parse_html_results(resp.text)

        except Exception as e:
            logger.error(f"FERC search failed: {e}")
            return []

    def search_form714(self, year: Optional[int] = None) -> list[FERCFiling]:
        """Search specifically for FERC Form 714 filings."""
        keyword = "Form 714"
        if year:
            keyword = f"Form 714 {year}"
        return self.search(keyword=keyword, category="Form 714")

    def search_transmission_plans(
        self,
        iso_name: Optional[str] = None,
    ) -> list[FERCFiling]:
        """Search for transmission planning studies."""
        keyword = "transmission plan"
        if iso_name:
            keyword = f"{iso_name} transmission plan"
        return self.search(keyword=keyword)

    def search_interconnection_studies(
        self,
        utility_name: Optional[str] = None,
    ) -> list[FERCFiling]:
        """Search for generator interconnection studies."""
        keyword = "generator interconnection"
        if utility_name:
            keyword = f"{utility_name} generator interconnection"
        return self.search(keyword=keyword)

    def download_document(
        self,
        accession_number: str,
        dest_dir: Path,
        filename: Optional[str] = None,
    ) -> Optional[Path]:
        """Download a FERC filing document."""
        dest_dir.mkdir(parents=True, exist_ok=True)
        fname = filename or f"ferc_{accession_number}.pdf"
        dest_path = dest_dir / fname

        if dest_path.exists():
            logger.info(f"Already downloaded: {fname}")
            return dest_path

        url = f"{FERC_DOWNLOAD_URL}?accession_number={accession_number}"
        logger.info(f"Downloading FERC filing {accession_number}...")

        try:
            resp = self._rate_limited_get(url, stream=True)
            with open(dest_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)
            logger.info(f"Saved to {dest_path}")
            return dest_path
        except Exception as e:
            logger.error(f"Download failed for {accession_number}: {e}")
            return None

    def _parse_json_results(self, data) -> list[FERCFiling]:
        """Parse JSON search results."""
        results = []
        items = data if isinstance(data, list) else data.get("filings", data.get("results", []))

        for item in items:
            filing = FERCFiling(
                accession_number=str(item.get("accessionNumber", item.get("accession_number", ""))),
                docket_number=item.get("docketNumber", item.get("docket_number")),
                description=item.get("description", item.get("title", ""))[:500],
                category=item.get("category"),
                filer=item.get("filer", item.get("company")),
            )

            # Parse date
            date_str = item.get("filingDate", item.get("filing_date"))
            if date_str:
                try:
                    filing.filing_date = datetime.strptime(date_str[:10], "%Y-%m-%d").date()
                except (ValueError, TypeError):
                    try:
                        filing.filing_date = datetime.strptime(date_str[:10], "%m/%d/%Y").date()
                    except (ValueError, TypeError):
                        pass

            results.append(filing)

        return results

    def _parse_html_results(self, html: str) -> list[FERCFiling]:
        """Parse HTML search results from FERC eLibrary."""
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")
        results = []

        # FERC eLibrary renders results in table rows
        for row in soup.find_all("tr"):
            cells = row.find_all("td")
            if len(cells) < 3:
                continue

            # Try to extract accession number (typically a link)
            accession = None
            for link in row.find_all("a", href=True):
                href = link["href"]
                if "accession" in href.lower():
                    match = re.search(r"(\d{8}-\d{4})", href)
                    if match:
                        accession = match.group(1)
                    else:
                        accession = link.get_text(strip=True)
                    break

            if not accession:
                # Try text patterns
                text = row.get_text()
                match = re.search(r"(\d{8}-\d{4})", text)
                if match:
                    accession = match.group(1)
                else:
                    continue

            # Extract other fields from cells
            texts = [c.get_text(strip=True) for c in cells]
            docket_match = re.search(r"([A-Z]{2}\d{2}-\d+)", " ".join(texts))

            filing = FERCFiling(
                accession_number=accession,
                docket_number=docket_match.group(1) if docket_match else None,
                description=texts[1][:500] if len(texts) > 1 else None,
            )

            # Try to parse date from cells
            for text in texts:
                try:
                    filing.filing_date = datetime.strptime(text.strip(), "%m/%d/%Y").date()
                    break
                except (ValueError, TypeError):
                    continue

            if not any(r.accession_number == accession for r in results):
                results.append(filing)

        return results

    def __repr__(self) -> str:
        return "<FERCeLibraryScraper>"
