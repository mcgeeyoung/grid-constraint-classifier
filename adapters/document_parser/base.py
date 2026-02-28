"""Base classes and data structures for document parsing pipeline.

Pipeline flow:
  Raw Document → Triage (classify type + relevance)
    → Excel/CSV: Direct table parsing via pandas/openpyxl
    → PDF with tables: Table extraction (tabula/pdfplumber) + LLM structuring
    → Narrative PDF: Text extraction + LLM summarization/extraction
    → Irrelevant: Skip
"""

import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)


class DocumentCategory(str, Enum):
    """Classification of a document for routing through the parse pipeline."""
    TABULAR_EXCEL = "tabular_excel"       # Excel/CSV with structured tables
    TABULAR_PDF = "tabular_pdf"           # PDF with extractable tables
    NARRATIVE_PDF = "narrative_pdf"        # Narrative/testimony PDF (LLM extraction)
    PROCEDURAL = "procedural"             # Procedural motion, order — low value
    SCANNED = "scanned"                   # Scanned image PDF (OCR needed)
    UNKNOWN = "unknown"


class ExtractionType(str, Enum):
    """Types of structured data we extract from documents."""
    LOAD_FORECAST = "load_forecast"
    GRID_CONSTRAINT = "grid_constraint"
    RESOURCE_NEED = "resource_need"
    HOSTING_CAPACITY = "hosting_capacity"
    AVOIDED_COST = "avoided_cost"
    RATE_SCHEDULE = "rate_schedule"
    GENERAL_SUMMARY = "general_summary"


class Confidence(str, Enum):
    """Confidence level for extracted data."""
    HIGH = "high"         # Direct table parsing, values clearly labeled
    MEDIUM = "medium"     # LLM extraction with high agreement
    LOW = "low"           # LLM extraction with ambiguity or missing context
    UNVERIFIED = "unverified"  # Needs human review


@dataclass
class ParsedTable:
    """A table extracted from a document."""
    df: pd.DataFrame
    page_number: Optional[int] = None
    table_index: int = 0
    title: Optional[str] = None
    confidence: Confidence = Confidence.MEDIUM
    source_method: str = ""  # tabula, pdfplumber, openpyxl, etc.


@dataclass
class ExtractedData:
    """Structured data extracted from a document via parsing or LLM."""
    extraction_type: ExtractionType
    data: dict                         # The extracted structured data (JSON-serializable)
    confidence: Confidence = Confidence.MEDIUM
    source_page: Optional[int] = None
    source_table_index: Optional[int] = None
    raw_text_snippet: Optional[str] = None  # Source text for provenance
    llm_model: Optional[str] = None    # Which model was used
    notes: Optional[str] = None


@dataclass
class DocumentParseResult:
    """Complete result from parsing a single document."""
    file_path: str
    category: DocumentCategory = DocumentCategory.UNKNOWN
    page_count: Optional[int] = None
    text_length: Optional[int] = None
    tables: list[ParsedTable] = field(default_factory=list)
    extractions: list[ExtractedData] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    status: str = "pending"  # pending, parsed, extracted, failed

    @property
    def has_tables(self) -> bool:
        return len(self.tables) > 0

    @property
    def has_extractions(self) -> bool:
        return len(self.extractions) > 0

    @property
    def high_confidence_extractions(self) -> list[ExtractedData]:
        return [e for e in self.extractions if e.confidence == Confidence.HIGH]

    @property
    def needs_review(self) -> bool:
        return any(e.confidence in (Confidence.LOW, Confidence.UNVERIFIED)
                   for e in self.extractions)
