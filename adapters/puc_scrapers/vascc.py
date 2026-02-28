"""Virginia State Corporation Commission (VA SCC) docket scraper.

VA SCC case search: https://scc.virginia.gov/docketsearch
Case information: https://scc.virginia.gov/pages/Case-Information

Case numbering: PUR-YYYY-NNNNN (e.g., PUR-2024-00063)
  PUR = Public Utility Regulation division
  PUE = Public Utility Environmental (older cases)

Key proceedings:
  Dominion Energy IRP: Filed every 3 years (most recent PUR-2023-00066)
  Dominion rate cases: PUR-YYYY-NNNNN
  AEP-Appalachian: PUR-YYYY-NNNNN
"""

import logging
import re
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from bs4 import BeautifulSoup

from .base import PUCScraper, DocketResult, FilingResult, DocumentResult

logger = logging.getLogger(__name__)


class VASCCScraper(PUCScraper):
    """Scraper for the Virginia State Corporation Commission."""

    state = "VA"
    puc_name = "Virginia State Corporation Commission"
    base_url = "https://scc.virginia.gov"

    DOCKET_SEARCH_URL = "https://scc.virginia.gov/docketsearch"
    CASE_API_URL = "https://scc.virginia.gov/DocketSearch/api"

    def search_dockets(
        self,
        utility_name: Optional[str] = None,
        filing_type: Optional[str] = None,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        keyword: Optional[str] = None,
    ) -> list[DocketResult]:
        """Search VA SCC dockets.

        The VA SCC docket search supports keyword, case number, and party name.
        """
        search_term = keyword or ""
        if filing_type:
            type_map = {
                "IRP": "integrated resource plan",
                "rate_case": "general rate",
                "DER": "distributed energy",
                "hosting_capacity": "hosting capacity",
                "interconnection": "interconnection",
            }
            search_term = type_map.get(filing_type, filing_type)

        if utility_name:
            search_term = f"{utility_name} {search_term}".strip()

        logger.info(f"VA SCC: searching for '{search_term}'")

        try:
            # VA SCC uses an API-like endpoint for search
            resp = self._rate_limited_get(
                f"{self.CASE_API_URL}/search",
                params={
                    "keyword": search_term,
                    "caseType": "PUR",
                },
            )

            # Try JSON response first
            if resp.headers.get("content-type", "").startswith("application/json"):
                return self._parse_json_results(resp.json())

            # Fallback to HTML parsing
            return self._parse_search_html(resp.text)

        except Exception as e:
            logger.warning(f"VA SCC API search failed ({e}), trying HTML scrape")
            try:
                resp = self._rate_limited_get(
                    self.DOCKET_SEARCH_URL,
                    params={"searchTerm": search_term},
                )
                return self._parse_search_html(resp.text)
            except Exception as e2:
                logger.error(f"VA SCC search failed: {e2}")
                return []

    def list_filings(self, docket_number: str) -> list[FilingResult]:
        """List filings in a VA SCC case."""
        logger.info(f"VA SCC: listing filings for {docket_number}")

        try:
            # Try API endpoint
            resp = self._rate_limited_get(
                f"{self.CASE_API_URL}/case/{docket_number}/documents",
            )

            if resp.headers.get("content-type", "").startswith("application/json"):
                return self._parse_json_filings(resp.json(), docket_number)

            return self._parse_filings_html(resp.text, docket_number)

        except Exception as e:
            logger.error(f"VA SCC filing list failed for {docket_number}: {e}")
            return []

    def download_document(
        self,
        document: DocumentResult,
        dest_dir: Path,
    ) -> Path:
        """Download a VA SCC document."""
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

    def _parse_json_results(self, data) -> list[DocketResult]:
        """Parse JSON search results from VA SCC API."""
        results = []
        items = data if isinstance(data, list) else data.get("results", data.get("cases", []))

        for item in items:
            case_num = item.get("caseNumber") or item.get("case_number", "")
            title = item.get("title") or item.get("description", "")

            result = DocketResult(
                docket_number=case_num,
                title=title[:500] if title else None,
                utility_name=item.get("companyName") or item.get("party"),
                source_url=f"{self.DOCKET_SEARCH_URL}#/case/{case_num}",
            )
            results.append(result)

        return results

    def _parse_search_html(self, html: str) -> list[DocketResult]:
        """Parse HTML search results page."""
        soup = BeautifulSoup(html, "html.parser")
        results = []

        # Look for case number patterns: PUR-YYYY-NNNNN or PUE-YYYY-NNNNN
        case_pattern = re.compile(r"(PU[RE])-(\d{4})-(\d{5})")

        for match in case_pattern.finditer(html):
            case_num = match.group(0)

            # Extract surrounding context for title
            start = max(0, match.start() - 100)
            end = min(len(html), match.end() + 300)
            context = html[start:end]

            # Try to find title text near the case number
            title = None
            clean = BeautifulSoup(context, "html.parser").get_text()
            title_match = re.search(rf"{re.escape(case_num)}\s*[-:]\s*(.+?)(?:\n|$)", clean)
            if title_match:
                title = title_match.group(1).strip()[:500]

            result = DocketResult(
                docket_number=case_num,
                title=title,
                source_url=f"{self.DOCKET_SEARCH_URL}#/case/{case_num}",
            )

            if not any(r.docket_number == case_num for r in results):
                results.append(result)

        return results

    def _parse_json_filings(self, data, docket_number: str) -> list[FilingResult]:
        """Parse JSON filing list from VA SCC API."""
        results = []
        items = data if isinstance(data, list) else data.get("documents", data.get("filings", []))

        for item in items:
            doc_id = str(item.get("id") or item.get("documentId", ""))
            title = item.get("title") or item.get("description", "")
            filed_date = None

            date_str = item.get("filedDate") or item.get("date")
            if date_str:
                try:
                    filed_date = datetime.strptime(date_str[:10], "%Y-%m-%d").date()
                except (ValueError, TypeError):
                    pass

            documents = []
            dl_url = item.get("downloadUrl") or item.get("url")
            if dl_url:
                fname = item.get("filename") or f"{doc_id}.pdf"
                documents.append(DocumentResult(
                    document_id=doc_id,
                    filename=fname,
                    download_url=dl_url if dl_url.startswith("http") else f"{self.base_url}{dl_url}",
                ))

            filing = FilingResult(
                filing_id=doc_id,
                docket_number=docket_number,
                title=title[:500] if title else None,
                filed_date=filed_date,
                filed_by=item.get("filedBy") or item.get("party"),
                documents=documents,
            )
            results.append(filing)

        return results

    def _parse_filings_html(self, html: str, docket_number: str) -> list[FilingResult]:
        """Parse HTML filing list page."""
        soup = BeautifulSoup(html, "html.parser")
        results = []

        for row in soup.find_all("tr"):
            cells = row.find_all("td")
            if len(cells) < 2:
                continue

            date_text = cells[0].get_text(strip=True)
            filed_date = None
            try:
                filed_date = datetime.strptime(date_text, "%m/%d/%Y").date()
            except (ValueError, TypeError):
                continue

            title = cells[1].get_text(strip=True) if len(cells) > 1 else None

            documents = []
            for link in row.find_all("a", href=True):
                href = link["href"]
                if href.endswith(".pdf") or "download" in href.lower():
                    documents.append(DocumentResult(
                        document_id=href.split("/")[-1],
                        filename=link.get_text(strip=True) or "document.pdf",
                        download_url=href if href.startswith("http") else f"{self.base_url}{href}",
                    ))

            filing = FilingResult(
                filing_id=f"{docket_number}_{date_text}_{len(results)}",
                docket_number=docket_number,
                title=title,
                filed_date=filed_date,
                documents=documents,
            )
            results.append(filing)

        return results

    def discover_active_dockets(
        self,
        filing_types: Optional[list[str]] = None,
    ) -> list[DocketResult]:
        """Return known active VA SCC proceedings."""
        known = [
            DocketResult(
                docket_number="PUR-2023-00066",
                title="Dominion Energy Virginia 2023 Integrated Resource Plan",
                utility_name="Dominion Energy Virginia",
                filing_type="IRP",
                status="open",
                source_url=f"{self.DOCKET_SEARCH_URL}#/case/PUR-2023-00066",
            ),
            DocketResult(
                docket_number="PUR-2024-00063",
                title="Dominion Energy Virginia Rate Case",
                utility_name="Dominion Energy Virginia",
                filing_type="rate_case",
                status="open",
                source_url=f"{self.DOCKET_SEARCH_URL}#/case/PUR-2024-00063",
            ),
        ]

        # Also try dynamic search for recent filings
        try:
            searched = self.search_dockets(
                utility_name="Dominion",
                keyword="integrated resource plan",
            )
            for d in searched:
                if not any(k.docket_number == d.docket_number for k in known):
                    known.append(d)
        except Exception as e:
            logger.warning(f"VA SCC dynamic search failed: {e}")

        return known
