"""Document triage: classify documents by type and relevance.

Routes documents through the appropriate parsing pipeline based on
file type, page count, and content characteristics.
"""

import logging
import mimetypes
from pathlib import Path
from typing import Optional

from .base import DocumentCategory

logger = logging.getLogger(__name__)

# Keywords that indicate high-value documents
HIGH_VALUE_KEYWORDS = {
    "load forecast", "peak demand", "energy forecast", "growth rate",
    "hosting capacity", "integration capacity", "distribution capacity",
    "grid constraint", "thermal limit", "voltage limit", "overload",
    "resource plan", "resource need", "capacity need", "procurement",
    "avoided cost", "marginal cost", "rate schedule",
    "grid needs assessment", "distribution resource plan",
    "integrated resource plan", "IRP", "DRP", "GNA",
}

# Keywords that indicate low-value/procedural documents
PROCEDURAL_KEYWORDS = {
    "motion to", "notice of", "certificate of service",
    "proof of service", "protective order", "scheduling order",
    "administrative law judge", "procedural ruling",
    "extension of time", "reply brief",
}


def classify_document(
    file_path: Path,
    extracted_text: Optional[str] = None,
    page_count: Optional[int] = None,
) -> DocumentCategory:
    """Classify a document for routing through the parse pipeline.

    Args:
        file_path: Path to the document file.
        extracted_text: First ~2000 chars of text if already extracted.
        page_count: Number of pages if known.

    Returns:
        DocumentCategory indicating how to process the document.
    """
    suffix = file_path.suffix.lower()
    mime = mimetypes.guess_type(str(file_path))[0] or ""

    # Excel/CSV files → direct table parsing
    if suffix in (".xlsx", ".xls", ".csv", ".tsv"):
        return DocumentCategory.TABULAR_EXCEL

    # Non-PDF files we don't handle
    if suffix not in (".pdf",):
        logger.debug(f"Unknown file type: {suffix}")
        return DocumentCategory.UNKNOWN

    # PDF classification requires more inspection
    if extracted_text:
        text_lower = extracted_text.lower()

        # Check for procedural content
        procedural_hits = sum(1 for kw in PROCEDURAL_KEYWORDS if kw in text_lower)
        if procedural_hits >= 2:
            return DocumentCategory.PROCEDURAL

        # Check for tabular content indicators
        table_indicators = (
            text_lower.count("|") > 10 or
            text_lower.count("\t") > 20 or
            any(kw in text_lower for kw in ("mw", "gwh", "kwh", "mwh")) and
            any(c.isdigit() for c in text_lower[:500])
        )

        if table_indicators:
            return DocumentCategory.TABULAR_PDF

        # Short PDFs with high-value keywords → tabular (likely has tables)
        if page_count and page_count <= 20:
            value_hits = sum(1 for kw in HIGH_VALUE_KEYWORDS if kw in text_lower)
            if value_hits >= 2:
                return DocumentCategory.TABULAR_PDF

        # Long narrative documents
        if page_count and page_count > 20:
            return DocumentCategory.NARRATIVE_PDF

        return DocumentCategory.NARRATIVE_PDF

    # No text available: classify by page count alone
    if page_count:
        if page_count <= 30:
            return DocumentCategory.TABULAR_PDF
        return DocumentCategory.NARRATIVE_PDF

    return DocumentCategory.UNKNOWN


def estimate_relevance(
    file_path: Path,
    extracted_text: Optional[str] = None,
    filing_type: Optional[str] = None,
) -> float:
    """Estimate document relevance on a 0-1 scale.

    Used to prioritize which documents to parse first.
    """
    score = 0.5  # Base score

    # Filing type boost
    high_value_types = {"IRP", "DRP", "GNA", "hosting_capacity", "rate_case"}
    if filing_type and filing_type in high_value_types:
        score += 0.2

    # File type boost
    suffix = file_path.suffix.lower()
    if suffix in (".xlsx", ".xls", ".csv"):
        score += 0.15  # Structured data is always more useful

    # Keyword analysis
    if extracted_text:
        text_lower = extracted_text[:5000].lower()
        value_hits = sum(1 for kw in HIGH_VALUE_KEYWORDS if kw in text_lower)
        score += min(value_hits * 0.05, 0.3)

        procedural_hits = sum(1 for kw in PROCEDURAL_KEYWORDS if kw in text_lower)
        score -= min(procedural_hits * 0.1, 0.4)

    return max(0.0, min(1.0, score))
