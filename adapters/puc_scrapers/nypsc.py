"""New York Public Service Commission (NYPSC) docket scraper.

Document & Matter Management System (DMM):
  https://documents.dps.ny.gov/public/Common/ViewDoc.aspx

Matter search: https://documents.dps.ny.gov/public/MatterManagement/MatterSearch.aspx
Document search: https://documents.dps.ny.gov/public/Common/SearchResults.aspx

Matter numbering: XX-XXXXX (e.g., 14-01299, 20-00340)

Key proceedings:
  14-01299: REV Track 2 (Reforming the Energy Vision)
  20-00340: Utility distribution system planning
  15-E-0302: ConEd Rate Case
  Various: Utility-specific rate cases and hosting capacity proceedings
"""

import logging
import re
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from bs4 import BeautifulSoup

from .base import PUCScraper, DocketResult, FilingResult, DocumentResult

logger = logging.getLogger(__name__)


class NYPSCScraper(PUCScraper):
    """Scraper for the New York Public Service Commission DMM system."""

    state = "NY"
    puc_name = "New York Public Service Commission"
    base_url = "https://documents.dps.ny.gov"

    MATTER_SEARCH_URL = "https://documents.dps.ny.gov/public/MatterManagement/MatterSearch.aspx"
    DOC_SEARCH_URL = "https://documents.dps.ny.gov/public/Common/SearchResults.aspx"
    MATTER_DETAIL_URL = "https://documents.dps.ny.gov/public/MatterManagement/CaseMaster.aspx"

    def search_dockets(
        self,
        utility_name: Optional[str] = None,
        filing_type: Optional[str] = None,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        keyword: Optional[str] = None,
    ) -> list[DocketResult]:
        """Search NY PSC matters via the DMM system.

        The NY DMM uses ASP.NET with ViewState, making direct scraping
        complex. We use a combination of URL params and HTML parsing.
        """
        search_term = keyword or ""
        if filing_type:
            type_map = {
                "IRP": "integrated resource",
                "rate_case": "rate case",
                "DER": "distributed energy",
                "hosting_capacity": "hosting capacity",
                "REV": "reforming the energy vision",
                "interconnection": "interconnection",
            }
            search_term = type_map.get(filing_type, filing_type)

        if utility_name:
            search_term = f"{utility_name} {search_term}".strip()

        logger.info(f"NY PSC: searching for '{search_term}'")

        try:
            resp = self._rate_limited_get(
                self.DOC_SEARCH_URL,
                params={"SearchText": search_term},
            )
            return self._parse_search_results(resp.text)
        except Exception as e:
            logger.error(f"NY PSC search failed: {e}")
            return []

    def list_filings(self, docket_number: str) -> list[FilingResult]:
        """List filings in a NY PSC matter."""
        logger.info(f"NY PSC: listing filings for {docket_number}")

        try:
            resp = self._rate_limited_get(
                self.MATTER_DETAIL_URL,
                params={"MatterCaseNo": docket_number},
            )
            return self._parse_matter_detail(resp.text, docket_number)
        except Exception as e:
            logger.error(f"NY PSC filing list failed for {docket_number}: {e}")
            return []

    def download_document(
        self,
        document: DocumentResult,
        dest_dir: Path,
    ) -> Path:
        """Download a NY PSC document."""
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
        """Parse NY PSC search results page."""
        soup = BeautifulSoup(html, "html.parser")
        results = []

        # NY PSC matter numbers: XX-XXXXX or XX-X-XXXX
        matter_pattern = re.compile(r"(\d{2})-([A-Z]?-?\d{4,5})")

        for match in matter_pattern.finditer(html):
            matter_num = match.group(0)

            start = max(0, match.start() - 100)
            end = min(len(html), match.end() + 300)
            context = BeautifulSoup(html[start:end], "html.parser").get_text()

            title = None
            title_match = re.search(
                rf"{re.escape(matter_num)}\s*[-:]\s*(.+?)(?:\n|$)",
                context,
            )
            if title_match:
                title = title_match.group(1).strip()[:500]

            result = DocketResult(
                docket_number=matter_num,
                title=title,
                source_url=f"{self.MATTER_DETAIL_URL}?MatterCaseNo={matter_num}",
            )

            if not any(r.docket_number == matter_num for r in results):
                results.append(result)

        return results

    def _parse_matter_detail(self, html: str, docket_number: str) -> list[FilingResult]:
        """Parse NY PSC matter detail page for filings."""
        soup = BeautifulSoup(html, "html.parser")
        results = []

        # Look for filing entries in table rows
        for row in soup.find_all("tr"):
            cells = row.find_all("td")
            if len(cells) < 3:
                continue

            # Try date parsing from cells
            filed_date = None
            for cell in cells[:2]:
                text = cell.get_text(strip=True)
                for fmt in ("%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d"):
                    try:
                        filed_date = datetime.strptime(text, fmt).date()
                        break
                    except (ValueError, TypeError):
                        continue
                if filed_date:
                    break

            if not filed_date:
                continue

            title = None
            filed_by = None
            for i, cell in enumerate(cells):
                text = cell.get_text(strip=True)
                if len(text) > 10 and not re.match(r"\d{1,2}/\d{1,2}/\d{2,4}", text):
                    if title is None:
                        title = text[:500]
                    elif filed_by is None:
                        filed_by = text[:200]

            documents = []
            for link in row.find_all("a", href=True):
                href = link["href"]
                if "ViewDoc" in href or href.endswith(".pdf"):
                    fname = link.get_text(strip=True) or "document.pdf"
                    if not fname.endswith(".pdf"):
                        fname = f"{fname}.pdf"
                    documents.append(DocumentResult(
                        document_id=href,
                        filename=fname,
                        download_url=href if href.startswith("http") else f"{self.base_url}{href}",
                    ))

            filing = FilingResult(
                filing_id=f"{docket_number}_{filed_date}_{len(results)}",
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
        """Return known active NY PSC proceedings for DER/grid topics."""
        known = [
            DocketResult(
                docket_number="14-01299",
                title="Reforming the Energy Vision (REV) Track 2",
                filing_type="REV",
                status="open",
                source_url=f"{self.MATTER_DETAIL_URL}?MatterCaseNo=14-01299",
            ),
            DocketResult(
                docket_number="20-00340",
                title="Distribution System Planning",
                filing_type="DRP",
                status="open",
                source_url=f"{self.MATTER_DETAIL_URL}?MatterCaseNo=20-00340",
            ),
            DocketResult(
                docket_number="15-E-0302",
                title="ConEd Rate Case and DER Integration",
                utility_name="Consolidated Edison",
                filing_type="rate_case",
                status="open",
                source_url=f"{self.MATTER_DETAIL_URL}?MatterCaseNo=15-E-0302",
            ),
            DocketResult(
                docket_number="20-E-0197",
                title="National Grid Rate Case",
                utility_name="National Grid",
                filing_type="rate_case",
                status="open",
                source_url=f"{self.MATTER_DETAIL_URL}?MatterCaseNo=20-E-0197",
            ),
        ]
        return known
