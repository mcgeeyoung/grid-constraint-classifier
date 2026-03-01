"""SMUD Board of Directors agenda scraper.

SMUD (Sacramento Municipal Utility District) is a community-owned utility
governed by an elected Board of Directors, not regulated by the CPUC. Board
agendas, committee materials, and meeting documents are published at:

  https://www.smud.org/Corporate/About-us/Company-Information/Board-Meetings

Archive (rolling 12 months):
  https://www.smud.org/Corporate/About-us/Company-Information/Board-Meetings/Board-Meeting-Archive

Meeting structure:
  - Board of Directors meetings (monthly, typically 3rd Thursday at 6 PM)
  - Finance & Audit Committee
  - Policy Committee
  - Energy Resources & Customer Services (ERCS) Committee
  - Strategic Development Committee

Document URL pattern:
  /-/media/Documents/Corporate/About-Us/Board-Meetings-and-Agendas/{YYYY}/{Mon}/{filename}.ashx

Docket numbering (synthetic):
  SMUD-BOD-YYYY-MM-DD   = Board of Directors meeting
  SMUD-ERCS-YYYY-MM-DD  = ERCS Committee
  SMUD-FIN-YYYY-MM-DD   = Finance & Audit Committee
  SMUD-POL-YYYY-MM-DD   = Policy Committee
  SMUD-SD-YYYY-MM-DD    = Strategic Development Committee
"""

import logging
import re
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from bs4 import BeautifulSoup

from .base import PUCScraper, DocketResult, FilingResult, DocumentResult

logger = logging.getLogger(__name__)

# Map committee names found in HTML to short codes
COMMITTEE_CODES = {
    "board of directors": "BOD",
    "finance": "FIN",
    "finance & audit": "FIN",
    "policy": "POL",
    "energy resources": "ERCS",
    "ercs": "ERCS",
    "strategic development": "SD",
}

# Month abbreviations used in SMUD URLs
MONTH_ABBREVS = {
    1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr", 5: "May", 6: "Jun",
    7: "Jul", 8: "Aug", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dec",
}

# DER/grid-relevant keywords for filtering agenda items
DER_KEYWORDS = [
    "distributed energy", "DER", "solar", "battery", "storage",
    "hosting capacity", "interconnection", "electric vehicle", "EV",
    "demand response", "load flexibility", "grid modernization",
    "resource plan", "IRP", "clean energy", "zero carbon",
    "community solar", "net metering", "rate design", "time of use",
    "wildfire", "resilience", "microgrid", "virtual power plant",
    "electrification", "building electrification", "heat pump",
    "2030 zero carbon", "capacity", "transmission", "substation",
]


class SMUDScraper(PUCScraper):
    """Scraper for SMUD Board of Directors meeting agendas and documents."""

    state = "CA_SMUD"
    puc_name = "SMUD Board of Directors"
    base_url = "https://www.smud.org"

    MEETINGS_URL = (
        "https://www.smud.org/Corporate/About-us/"
        "Company-Information/Board-Meetings"
    )
    ARCHIVE_URL = (
        "https://www.smud.org/Corporate/About-us/"
        "Company-Information/Board-Meetings/Board-Meeting-Archive"
    )
    DOCS_BASE = "/-/media/Documents/Corporate/About-Us/Board-Meetings-and-Agendas"

    def search_dockets(
        self,
        utility_name: Optional[str] = None,
        filing_type: Optional[str] = None,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        keyword: Optional[str] = None,
    ) -> list[DocketResult]:
        """Search SMUD board meetings.

        Since SMUD doesn't have a search API, this scrapes the archive and
        current meetings pages, then filters by keyword and date range.
        """
        meetings = self._scrape_meetings()

        # Filter by date range
        if date_from:
            meetings = [m for m in meetings if m.opened_date and m.opened_date >= date_from]
        if date_to:
            meetings = [m for m in meetings if m.opened_date and m.opened_date <= date_to]

        # Filter by committee type
        if filing_type:
            code = filing_type.upper()
            meetings = [m for m in meetings if code in m.docket_number]

        # Filter by keyword in title
        if keyword:
            kw_lower = keyword.lower()
            meetings = [m for m in meetings if m.title and kw_lower in m.title.lower()]

        logger.info(f"SMUD: found {len(meetings)} meetings matching criteria")
        return meetings

    def list_filings(self, docket_number: str) -> list[FilingResult]:
        """List documents for a specific SMUD board meeting.

        Accepts both full docket numbers (SMUD-BOD-2026-01-15) and prefix
        patterns (SMUD-BOD) used by the watchlist. Prefix patterns return
        all recent documents for that committee type.
        """
        logger.info(f"SMUD: listing documents for {docket_number}")

        parts = docket_number.split("-")
        committee = parts[1] if len(parts) >= 2 else "BOD"

        # Full docket number with date: SMUD-BOD-2026-01-15
        if len(parts) >= 5:
            try:
                meeting_date = date(int(parts[2]), int(parts[3]), int(parts[4]))
            except (ValueError, IndexError):
                logger.error(f"Cannot parse date from docket: {docket_number}")
                return []

            try:
                resp = self._rate_limited_get(self.ARCHIVE_URL)
                return self._extract_meeting_documents(
                    resp.text, meeting_date, committee, docket_number,
                )
            except Exception as e:
                logger.error(f"Failed to list SMUD filings for {docket_number}: {e}")
                return []

        # Prefix-only pattern (SMUD-BOD, SMUD-ERCS): return all recent
        # documents for this committee from the archive page
        try:
            resp = self._rate_limited_get(self.ARCHIVE_URL)
            return self._extract_committee_documents(resp.text, committee)
        except Exception as e:
            logger.error(f"Failed to list SMUD filings for {docket_number}: {e}")
            return []

    def _extract_committee_documents(
        self, html: str, committee: str,
    ) -> list[FilingResult]:
        """Extract all documents for a committee from the archive page."""
        soup = BeautifulSoup(html, "html.parser")
        filings = []

        doc_links = soup.find_all(
            "a", href=re.compile(r"Board-Meetings-and-Agendas.*\.ashx"),
        )

        for link in doc_links:
            href = link.get("href", "")
            text = link.get_text(strip=True)

            if not self._doc_matches_committee(href, text, committee):
                continue

            # Try to extract date from URL
            date_match = re.search(r"(\d{4})-(\d{2})-(\d{2})", href)
            filed_date = None
            if date_match:
                try:
                    filed_date = date(
                        int(date_match.group(1)),
                        int(date_match.group(2)),
                        int(date_match.group(3)),
                    )
                except ValueError:
                    pass

            doc_url = href if href.startswith("http") else f"{self.base_url}{href}"
            filename = href.split("/")[-1].replace(".ashx", ".pdf")
            docket = f"SMUD-{committee}"
            if filed_date:
                docket = f"SMUD-{committee}-{filed_date.isoformat()}"

            doc = DocumentResult(
                document_id=href.split("/")[-1],
                filename=filename,
                mime_type="application/pdf",
                download_url=doc_url,
            )

            filing = FilingResult(
                filing_id=f"{docket}_{len(filings)}",
                docket_number=docket,
                title=text or filename,
                filed_date=filed_date,
                filed_by="SMUD",
                document_type=self._classify_doc_type(text),
                source_url=doc_url,
                documents=[doc],
            )
            filings.append(filing)

        logger.info(f"SMUD: found {len(filings)} {committee} documents in archive")
        return filings

    @staticmethod
    def _classify_doc_type(text: str) -> str:
        """Classify document type from link text."""
        text_lower = text.lower()
        if "agenda" in text_lower:
            return "agenda"
        if "information packet" in text_lower or "info packet" in text_lower:
            return "info_packet"
        if "exhibit" in text_lower:
            return "exhibit"
        if "notice" in text_lower:
            return "notice"
        if "compensation" in text_lower:
            return "compensation"
        if "minutes" in text_lower:
            return "minutes"
        return "other"

    def download_document(
        self,
        document: DocumentResult,
        dest_dir: Path,
    ) -> Path:
        """Download a SMUD board document."""
        dest_dir.mkdir(parents=True, exist_ok=True)

        # Clean filename for filesystem
        safe_name = re.sub(r'[^\w\-.]', '_', document.filename)
        if not safe_name.endswith('.pdf'):
            safe_name += '.pdf'
        dest_path = dest_dir / safe_name

        if dest_path.exists():
            logger.info(f"Already downloaded: {safe_name}")
            document.local_path = str(dest_path)
            return dest_path

        url = document.download_url
        if not url.startswith("http"):
            url = f"{self.base_url}{url}"

        logger.info(f"Downloading {safe_name}...")
        resp = self._rate_limited_get(url, stream=True)

        with open(dest_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)

        document.local_path = str(dest_path)
        size_kb = dest_path.stat().st_size / 1024
        logger.info(f"Saved to {dest_path} ({size_kb:.0f} KB)")
        return dest_path

    def discover_active_dockets(
        self,
        filing_types: Optional[list[str]] = None,
    ) -> list[DocketResult]:
        """Return recent SMUD board meetings with DER/grid-relevant agenda items.

        Scrapes both current and archive pages, then filters for meetings
        that contain energy/grid-relevant topics in their documents.
        """
        all_meetings = self._scrape_meetings()

        # If filtering by committee type
        if filing_types:
            codes = {ft.upper() for ft in filing_types}
            all_meetings = [
                m for m in all_meetings
                if any(c in m.docket_number for c in codes)
            ]

        # Filter to meetings likely relevant to DER/grid work
        relevant = []
        for meeting in all_meetings:
            if meeting.title and any(
                kw.lower() in meeting.title.lower() for kw in DER_KEYWORDS
            ):
                relevant.append(meeting)
            elif "ERCS" in meeting.docket_number or "BOD" in meeting.docket_number:
                # ERCS and BOD meetings are always potentially relevant
                relevant.append(meeting)

        logger.info(
            f"SMUD: {len(relevant)} relevant meetings "
            f"(of {len(all_meetings)} total)"
        )
        return relevant

    def _scrape_meetings(self) -> list[DocketResult]:
        """Scrape both current and archive pages for meetings."""
        meetings = []

        for url in [self.MEETINGS_URL, self.ARCHIVE_URL]:
            try:
                resp = self._rate_limited_get(url)
                page_meetings = self._parse_meetings_page(resp.text)
                meetings.extend(page_meetings)
            except Exception as e:
                logger.warning(f"Failed to scrape {url}: {e}")

        # Deduplicate by docket number
        seen = set()
        unique = []
        for m in meetings:
            if m.docket_number not in seen:
                seen.add(m.docket_number)
                unique.append(m)

        return sorted(unique, key=lambda m: m.opened_date or date.min, reverse=True)

    def _parse_meetings_page(self, html: str) -> list[DocketResult]:
        """Parse a SMUD meetings page and extract meeting entries."""
        soup = BeautifulSoup(html, "html.parser")
        results = []

        # Find all links to .ashx documents (agenda PDFs)
        doc_links = soup.find_all("a", href=re.compile(r"Board-Meetings-and-Agendas.*\.ashx"))

        # Group documents by meeting date
        meetings_by_key: dict[str, dict] = {}

        for link in doc_links:
            href = link.get("href", "")
            text = link.get_text(strip=True)

            # Extract date from URL: /YYYY/Mon/YYYY-MM-DD_...
            date_match = re.search(r"/(\d{4})/\w+/(\d{4})-(\d{2})-(\d{2})_", href)
            if not date_match:
                # Try alternate pattern: /YYYY/Mon/SomeDoc.ashx
                year_month_match = re.search(r"/(\d{4})/(\w+)/", href)
                if year_month_match:
                    # Can't determine exact date from this pattern, skip
                    continue
                continue

            year = int(date_match.group(2))
            month = int(date_match.group(3))
            day = int(date_match.group(4))

            try:
                meeting_date = date(year, month, day)
            except ValueError:
                continue

            # Determine committee from URL/text
            committee = self._classify_committee(href, text)
            key = f"SMUD-{committee}-{year:04d}-{month:02d}-{day:02d}"

            if key not in meetings_by_key:
                meetings_by_key[key] = {
                    "date": meeting_date,
                    "committee": committee,
                    "docs": [],
                }
            meetings_by_key[key]["docs"].append(text)

        # Convert to DocketResults
        for docket_num, info in meetings_by_key.items():
            committee = info["committee"]
            committee_name = {
                "BOD": "Board of Directors",
                "FIN": "Finance & Audit Committee",
                "POL": "Policy Committee",
                "ERCS": "Energy Resources & Customer Services Committee",
                "SD": "Strategic Development Committee",
            }.get(committee, committee)

            # Build title from document names
            doc_titles = [d for d in info["docs"] if "Exhibit" in d or "Item" in d]
            if doc_titles:
                title = f"{committee_name}: {'; '.join(doc_titles[:3])}"
                if len(doc_titles) > 3:
                    title += f" (+{len(doc_titles) - 3} more)"
            else:
                title = f"{committee_name} Meeting"

            results.append(DocketResult(
                docket_number=docket_num,
                title=title[:500],
                utility_name="SMUD",
                filing_type=committee,
                status="open",
                opened_date=info["date"],
                source_url=self.ARCHIVE_URL,
            ))

        return results

    def _extract_meeting_documents(
        self,
        html: str,
        meeting_date: date,
        committee: str,
        docket_number: str,
    ) -> list[FilingResult]:
        """Extract all documents for a specific meeting from the archive page."""
        soup = BeautifulSoup(html, "html.parser")
        filings = []

        date_str = meeting_date.strftime("%Y-%m-%d")
        doc_links = soup.find_all("a", href=re.compile(r"Board-Meetings-and-Agendas.*\.ashx"))

        for link in doc_links:
            href = link.get("href", "")
            text = link.get_text(strip=True)

            # Match documents for this specific date
            if date_str not in href:
                # Also check for non-dated docs in the right month folder
                month_abbrev = MONTH_ABBREVS.get(meeting_date.month, "")
                year_str = str(meeting_date.year)
                if f"/{year_str}/{month_abbrev}/" not in href:
                    continue
                # For non-dated docs, check committee relevance
                if not self._doc_matches_committee(href, text, committee):
                    continue

            # Skip if wrong committee
            if date_str in href and not self._doc_matches_committee(href, text, committee):
                continue

            doc_url = href if href.startswith("http") else f"{self.base_url}{href}"

            doc_type = self._classify_doc_type(text)

            # Create a filename from the URL
            filename = href.split("/")[-1].replace(".ashx", ".pdf")

            doc = DocumentResult(
                document_id=href.split("/")[-1],
                filename=filename,
                mime_type="application/pdf",
                download_url=doc_url,
            )

            filing = FilingResult(
                filing_id=f"{docket_number}_{doc_type}_{len(filings)}",
                docket_number=docket_number,
                title=text or filename,
                filed_date=meeting_date,
                filed_by="SMUD",
                document_type=doc_type,
                source_url=doc_url,
                documents=[doc],
            )
            filings.append(filing)

        logger.info(
            f"SMUD: found {len(filings)} documents for "
            f"{committee} meeting on {date_str}"
        )
        return filings

    @staticmethod
    def _classify_committee(href: str, text: str) -> str:
        """Determine which committee a document belongs to."""
        combined = f"{href} {text}".lower()

        # Check explicit committee indicators in URL/text
        if "finance" in combined or "audit" in combined or "_finance_" in combined.replace("-", "_"):
            return "FIN"
        if "policy" in combined or "_policy_" in combined.replace("-", "_"):
            return "POL"
        if "ercs" in combined or "energy resources" in combined:
            return "ERCS"
        if "strategic" in combined:
            return "SD"
        if "bod" in combined or "board of directors" in combined:
            return "BOD"

        # Default: if it has Agenda_BOD in URL, it's BOD
        if "agenda_bod" in combined.replace("-", "").lower():
            return "BOD"

        return "BOD"  # Default to Board of Directors

    @staticmethod
    def _doc_matches_committee(href: str, text: str, committee: str) -> bool:
        """Check if a document belongs to the specified committee."""
        classified = SMUDScraper._classify_committee(href, text)
        return classified == committee
