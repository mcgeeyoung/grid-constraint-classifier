"""California Public Utilities Commission (CPUC) docket scraper.

CPUC eFiling system: https://apps.cpuc.ca.gov/apex/f?p=401
Proceedings search: https://apps.cpuc.ca.gov/apex/f?p=401:56

Docket numbering:
  R.XX-YY-ZZZ  = Rulemaking (policy/rulemaking proceedings)
  A.XX-YY-ZZZ  = Application (utility filings, rate cases, IRPs)
  I.XX-YY-ZZZ  = Investigation
  C.XX-YY-ZZZ  = Complaint

Key active proceedings for DER/grid:
  R.21-06-017  = Interconnection (Rule 21)
  R.20-05-003  = IRP (Integrated Resource Plan)
  R.14-08-013  = DRP (Distribution Resources Plan)
  R.22-07-005  = DER action plan
  A.XX-XX-XXX  = Utility GRC filings (PG&E, SCE, SDG&E)

Also exposes a data portal: https://www.cpuc.ca.gov/about-cpuc/divisions/
"""

import logging
import re
from datetime import date, datetime
from pathlib import Path
from typing import Optional
from urllib.parse import urlencode

from bs4 import BeautifulSoup

from .base import PUCScraper, DocketResult, FilingResult, DocumentResult

logger = logging.getLogger(__name__)


class CPUCScraper(PUCScraper):
    """Scraper for the California Public Utilities Commission eFiling system."""

    state = "CA"
    puc_name = "California Public Utilities Commission"
    base_url = "https://apps.cpuc.ca.gov"

    # APEX app URLs
    PROCEEDINGS_SEARCH_URL = "https://apps.cpuc.ca.gov/apex/f?p=401:56"
    PROCEEDING_DETAIL_URL = "https://apps.cpuc.ca.gov/apex/f?p=401:57"
    DOCUMENT_SEARCH_URL = "https://apps.cpuc.ca.gov/apex/f?p=401:58"

    # Alternative: CPUC published proceedings list (JSON-friendly)
    PROCEEDINGS_API_URL = "https://apps.cpuc.ca.gov/apex/f"

    def search_dockets(
        self,
        utility_name: Optional[str] = None,
        filing_type: Optional[str] = None,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        keyword: Optional[str] = None,
    ) -> list[DocketResult]:
        """Search CPUC proceedings.

        CPUC proceedings are searchable via the APEX application.
        We scrape the search results page for proceeding numbers.
        """
        params = {"p": "401:56:0"}

        # Build search by keyword or proceeding type
        search_term = keyword or ""
        if filing_type:
            type_map = {
                "IRP": "Integrated Resource Plan",
                "DRP": "Distribution Resources Plan",
                "GNA": "Grid Needs Assessment",
                "rate_case": "General Rate Case",
                "hosting_capacity": "hosting capacity",
                "DER": "distributed energy",
                "interconnection": "interconnection",
            }
            search_term = type_map.get(filing_type, filing_type)

        if utility_name:
            search_term = f"{utility_name} {search_term}".strip()

        logger.info(f"CPUC: searching for '{search_term}'")

        try:
            resp = self._rate_limited_get(
                self.PROCEEDINGS_SEARCH_URL,
                params={"p_search": search_term} if search_term else None,
            )
            return self._parse_proceedings_page(resp.text)
        except Exception as e:
            logger.error(f"CPUC search failed: {e}")
            return []

    def list_filings(self, docket_number: str) -> list[FilingResult]:
        """List filings in a CPUC proceeding.

        Accesses the proceeding detail page and extracts filing entries.
        """
        logger.info(f"CPUC: listing filings for {docket_number}")

        # CPUC proceeding detail URLs use the proceeding number
        # e.g., https://apps.cpuc.ca.gov/apex/f?p=401:57:::NO:57:P57_PROCEEDING_ID:R2106017
        proc_id = docket_number.replace(".", "").replace("-", "")

        try:
            url = f"{self.PROCEEDING_DETAIL_URL}:::NO:57:P57_PROCEEDING_ID:{proc_id}"
            resp = self._rate_limited_get(url)
            return self._parse_filings_page(resp.text, docket_number)
        except Exception as e:
            logger.error(f"CPUC filing list failed for {docket_number}: {e}")
            return []

    def download_document(
        self,
        document: DocumentResult,
        dest_dir: Path,
    ) -> Path:
        """Download a CPUC document."""
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_path = dest_dir / document.filename

        if dest_path.exists():
            logger.info(f"Already downloaded: {document.filename}")
            document.local_path = str(dest_path)
            return dest_path

        logger.info(f"Downloading {document.filename}...")
        resp = self._rate_limited_get(document.download_url, stream=True)

        with open(dest_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)

        document.local_path = str(dest_path)
        logger.info(f"Saved to {dest_path} ({dest_path.stat().st_size / 1024:.0f} KB)")
        return dest_path

    def _parse_proceedings_page(self, html: str) -> list[DocketResult]:
        """Parse CPUC proceedings search results page."""
        soup = BeautifulSoup(html, "html.parser")
        results = []

        # CPUC APEX app renders proceedings in a table or report region
        # Look for proceeding number patterns in the page
        proc_pattern = re.compile(r"([RAIC])\.\s*(\d{2})-(\d{2})-(\d{3})")

        for match in proc_pattern.finditer(html):
            proc_type = match.group(1)
            proc_num = f"{proc_type}.{match.group(2)}-{match.group(3)}-{match.group(4)}"

            # Try to find surrounding context for title
            start = max(0, match.start() - 200)
            end = min(len(html), match.end() + 500)
            context = html[start:end]

            # Extract title if available
            title = None
            title_match = re.search(
                rf"{re.escape(proc_num)}[^<]*?([A-Z][^<]{{10,200}})",
                context,
            )
            if title_match:
                title = title_match.group(1).strip()[:500]

            type_map = {"R": "rulemaking", "A": "application",
                        "I": "investigation", "C": "complaint"}

            result = DocketResult(
                docket_number=proc_num,
                title=title,
                filing_type=type_map.get(proc_type, "unknown"),
                source_url=f"{self.PROCEEDING_DETAIL_URL}:::NO:57:P57_PROCEEDING_ID:{proc_num.replace('.', '').replace('-', '')}",
            )

            # Deduplicate
            if not any(r.docket_number == proc_num for r in results):
                results.append(result)

        logger.info(f"CPUC: parsed {len(results)} proceedings from page")
        return results

    def _parse_filings_page(self, html: str, docket_number: str) -> list[FilingResult]:
        """Parse CPUC proceeding detail page for individual filings."""
        soup = BeautifulSoup(html, "html.parser")
        results = []

        # Look for filing entries - CPUC typically renders them in table rows
        # Each filing has a date, title, filed_by, and document links
        rows = soup.find_all("tr")

        for row in rows:
            cells = row.find_all("td")
            if len(cells) < 3:
                continue

            # Try to extract date from first cell
            date_text = cells[0].get_text(strip=True)
            filed_date = None
            try:
                filed_date = datetime.strptime(date_text, "%m/%d/%Y").date()
            except (ValueError, TypeError):
                try:
                    filed_date = datetime.strptime(date_text, "%m/%d/%y").date()
                except (ValueError, TypeError):
                    continue  # Skip rows without valid dates

            # Title is typically in second or third cell
            title = cells[1].get_text(strip=True) if len(cells) > 1 else None
            filed_by = cells[2].get_text(strip=True) if len(cells) > 2 else None

            # Look for document download links
            documents = []
            for link in row.find_all("a", href=True):
                href = link["href"]
                if "download" in href.lower() or href.endswith(".pdf"):
                    doc = DocumentResult(
                        document_id=href.split("/")[-1] if "/" in href else href,
                        filename=link.get_text(strip=True) or "document.pdf",
                        download_url=href if href.startswith("http") else f"{self.base_url}{href}",
                    )
                    documents.append(doc)

            filing = FilingResult(
                filing_id=f"{docket_number}_{date_text}_{len(results)}",
                docket_number=docket_number,
                title=title,
                filed_date=filed_date,
                filed_by=filed_by,
                documents=documents,
            )
            results.append(filing)

        logger.info(f"CPUC: parsed {len(results)} filings for {docket_number}")
        return results

    def discover_active_dockets(
        self,
        filing_types: Optional[list[str]] = None,
    ) -> list[DocketResult]:
        """Return known active CPUC proceedings for DER/grid topics."""
        # Start with curated list of known active proceedings
        known = [
            DocketResult(
                docket_number="R.21-06-017",
                title="Order Instituting Rulemaking to Advance Demand Flexibility Through Electric Rates",
                filing_type="DER",
                status="open",
                source_url=f"{self.PROCEEDING_DETAIL_URL}:::NO:57:P57_PROCEEDING_ID:R2106017",
            ),
            DocketResult(
                docket_number="R.20-05-003",
                title="Order Instituting Rulemaking to Continue the Development of the Integrated Resource Planning Process",
                filing_type="IRP",
                status="open",
                source_url=f"{self.PROCEEDING_DETAIL_URL}:::NO:57:P57_PROCEEDING_ID:R2005003",
            ),
            DocketResult(
                docket_number="R.14-08-013",
                title="Order Instituting Rulemaking Regarding Policies and Rules for Development of Distribution Resources Plans",
                filing_type="DRP",
                status="open",
                source_url=f"{self.PROCEEDING_DETAIL_URL}:::NO:57:P57_PROCEEDING_ID:R1408013",
            ),
            DocketResult(
                docket_number="R.22-07-005",
                title="Order Instituting Rulemaking to Modernize the Electric Grid for a High Distributed Energy Resources Future",
                filing_type="DER",
                status="open",
                source_url=f"{self.PROCEEDING_DETAIL_URL}:::NO:57:P57_PROCEEDING_ID:R2207005",
            ),
        ]

        # Also try dynamic search
        try:
            searched = self.search_dockets(keyword="hosting capacity")
            for d in searched:
                if not any(k.docket_number == d.docket_number for k in known):
                    known.append(d)
        except Exception as e:
            logger.warning(f"CPUC dynamic search failed: {e}")

        return known
