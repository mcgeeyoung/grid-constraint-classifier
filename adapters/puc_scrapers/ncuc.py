"""North Carolina Utilities Commission (NCUC) docket scraper.

NCUC eFiling: https://starw1.ncuc.gov/NCUC/page/docket-docs/
Search: By docket number, party name, or keyword

Docket numbering: E-100 Sub NNN (general electric), E-2 Sub NNN (Duke Carolinas),
  E-7 Sub NNN (Duke Progress), SP-XXX Sub NNN (solar/DER)

Key proceedings:
  E-100 Sub 190 (and subsequent): Duke Energy Carolina/Progress IRP
  E-100 Sub 179: CPRE Program (competitive solar procurement)
  E-2 Sub XXXX: Duke Energy Carolinas proceedings
  E-7 Sub XXXX: Duke Energy Progress proceedings
"""

import logging
import re
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from bs4 import BeautifulSoup

from .base import PUCScraper, DocketResult, FilingResult, DocumentResult

logger = logging.getLogger(__name__)


class NCUCScraper(PUCScraper):
    """Scraper for the North Carolina Utilities Commission."""

    state = "NC"
    puc_name = "North Carolina Utilities Commission"
    base_url = "https://starw1.ncuc.gov"

    DOCKET_SEARCH_URL = "https://starw1.ncuc.gov/NCUC/page/docket-docs/"
    DOCKET_API_URL = "https://starw1.ncuc.gov/NCUC/ViewFile.aspx"

    def search_dockets(
        self,
        utility_name: Optional[str] = None,
        filing_type: Optional[str] = None,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        keyword: Optional[str] = None,
    ) -> list[DocketResult]:
        """Search NCUC dockets."""
        search_term = keyword or ""
        if filing_type:
            type_map = {
                "IRP": "integrated resource plan",
                "rate_case": "general rate case",
                "DER": "distributed energy",
                "hosting_capacity": "hosting capacity",
                "solar": "solar",
                "CPRE": "competitive procurement",
            }
            search_term = type_map.get(filing_type, filing_type)

        if utility_name:
            search_term = f"{utility_name} {search_term}".strip()

        logger.info(f"NCUC: searching for '{search_term}'")

        try:
            resp = self._rate_limited_get(
                self.DOCKET_SEARCH_URL,
                params={"search": search_term},
            )
            return self._parse_search_results(resp.text)
        except Exception as e:
            logger.error(f"NCUC search failed: {e}")
            return []

    def list_filings(self, docket_number: str) -> list[FilingResult]:
        """List filings in an NCUC docket."""
        logger.info(f"NCUC: listing filings for {docket_number}")

        try:
            resp = self._rate_limited_get(
                self.DOCKET_SEARCH_URL,
                params={"docket": docket_number},
            )
            return self._parse_filings_page(resp.text, docket_number)
        except Exception as e:
            logger.error(f"NCUC filing list failed for {docket_number}: {e}")
            return []

    def download_document(
        self,
        document: DocumentResult,
        dest_dir: Path,
    ) -> Path:
        """Download an NCUC document."""
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
        return dest_path

    def _parse_search_results(self, html: str) -> list[DocketResult]:
        """Parse NCUC docket search results."""
        results = []

        # NCUC docket patterns: E-100 Sub 190, E-2 Sub 1300, SP-100 Sub 5
        docket_pattern = re.compile(r"([A-Z]+-\d+)\s+Sub\s+(\d+)")

        for match in docket_pattern.finditer(html):
            docket_num = f"{match.group(1)} Sub {match.group(2)}"

            # Extract context for title
            start = max(0, match.start() - 100)
            end = min(len(html), match.end() + 300)
            context = BeautifulSoup(html[start:end], "html.parser").get_text()

            title = None
            title_match = re.search(
                rf"Sub\s+{match.group(2)}\s*[-:]\s*(.+?)(?:\n|$)",
                context,
            )
            if title_match:
                title = title_match.group(1).strip()[:500]

            result = DocketResult(
                docket_number=docket_num,
                title=title,
                source_url=f"{self.DOCKET_SEARCH_URL}?docket={docket_num.replace(' ', '+')}",
            )

            if not any(r.docket_number == docket_num for r in results):
                results.append(result)

        return results

    def _parse_filings_page(self, html: str, docket_number: str) -> list[FilingResult]:
        """Parse NCUC docket detail page for filings."""
        soup = BeautifulSoup(html, "html.parser")
        results = []

        for row in soup.find_all("tr"):
            cells = row.find_all("td")
            if len(cells) < 2:
                continue

            date_text = cells[0].get_text(strip=True)
            filed_date = None
            for fmt in ("%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d"):
                try:
                    filed_date = datetime.strptime(date_text, fmt).date()
                    break
                except (ValueError, TypeError):
                    continue
            if not filed_date:
                continue

            title = cells[1].get_text(strip=True) if len(cells) > 1 else None
            filed_by = cells[2].get_text(strip=True) if len(cells) > 2 else None

            documents = []
            for link in row.find_all("a", href=True):
                href = link["href"]
                if href.endswith(".pdf") or "ViewFile" in href or "download" in href.lower():
                    documents.append(DocumentResult(
                        document_id=href.split("/")[-1] if "/" in href else href,
                        filename=link.get_text(strip=True) or "document.pdf",
                        download_url=href if href.startswith("http") else f"{self.base_url}{href}",
                    ))

            filing = FilingResult(
                filing_id=f"{docket_number}_{date_text}_{len(results)}",
                docket_number=docket_number,
                title=title,
                filed_date=filed_date,
                filed_by=filed_by,
                documents=documents,
            )
            results.append(filing)

        return results

    def discover_active_dockets(
        self,
        filing_types: Optional[list[str]] = None,
    ) -> list[DocketResult]:
        """Return known active NCUC proceedings."""
        known = [
            DocketResult(
                docket_number="E-100 Sub 190",
                title="2023 Biennial Integrated Resource Plans and Carbon Plan",
                utility_name="Duke Energy Carolinas/Duke Energy Progress",
                filing_type="IRP",
                status="open",
            ),
            DocketResult(
                docket_number="E-100 Sub 179",
                title="Competitive Procurement of Renewable Energy (CPRE)",
                utility_name="Duke Energy",
                filing_type="DER",
                status="open",
            ),
            DocketResult(
                docket_number="E-100 Sub 101",
                title="Avoided Cost and Interconnection Standards",
                filing_type="interconnection",
                status="open",
            ),
        ]
        return known
