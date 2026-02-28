"""Document parsing pipeline orchestrator.

Coordinates triage, parsing, and extraction across the full pipeline:
  1. Classify document (triage)
  2. Extract text/tables (pdf_parser or excel_parser)
  3. Optionally run LLM extraction (llm_extractor)
  4. Return structured results
"""

import logging
from pathlib import Path
from typing import Optional

from .base import (
    Confidence, DocumentCategory, DocumentParseResult,
    ExtractionType, ExtractedData, ParsedTable,
)
from .triage import classify_document, estimate_relevance
from .pdf_parser import extract_text, extract_tables
from .excel_parser import parse_excel, detect_table_type
from .llm_extractor import extract_with_llm, extract_table_with_llm

logger = logging.getLogger(__name__)


def parse_document(
    file_path: Path,
    utility_name: Optional[str] = None,
    filing_type: Optional[str] = None,
    run_llm: bool = False,
    llm_extraction_types: Optional[list[str]] = None,
    max_pages: Optional[int] = None,
) -> DocumentParseResult:
    """Parse a document through the full pipeline.

    Args:
        file_path: Path to the document.
        utility_name: Utility name for LLM context.
        filing_type: Filing type for relevance scoring.
        run_llm: Whether to run LLM extraction.
        llm_extraction_types: Specific extraction types to run.
            If None, auto-detects from table content.
        max_pages: Max PDF pages to process.

    Returns:
        DocumentParseResult with tables and extractions.
    """
    result = DocumentParseResult(file_path=str(file_path))

    if not file_path.exists():
        result.errors.append(f"File not found: {file_path}")
        result.status = "failed"
        return result

    # Step 1: Extract text (for triage)
    suffix = file_path.suffix.lower()
    text = ""
    page_count = None

    if suffix == ".pdf":
        text, page_count = extract_text(file_path, max_pages=max_pages or 5)
        result.page_count = page_count
        result.text_length = len(text)
    elif suffix in (".xlsx", ".xls", ".csv", ".tsv"):
        pass  # No text extraction needed for structured files

    # Step 2: Classify
    result.category = classify_document(
        file_path, extracted_text=text[:2000] if text else None, page_count=page_count
    )
    logger.info(f"Classified {file_path.name} as {result.category.value}")

    # Step 3: Route to appropriate parser
    try:
        if result.category == DocumentCategory.TABULAR_EXCEL:
            result.tables = parse_excel(file_path)

        elif result.category == DocumentCategory.TABULAR_PDF:
            # Extract tables
            result.tables = extract_tables(file_path)

            # Also get full text for LLM if needed
            if run_llm and not text:
                text, page_count = extract_text(file_path, max_pages=max_pages)
                result.page_count = page_count
                result.text_length = len(text)

        elif result.category == DocumentCategory.NARRATIVE_PDF:
            # Full text extraction for LLM processing
            if not text:
                text, page_count = extract_text(file_path, max_pages=max_pages)
                result.page_count = page_count
                result.text_length = len(text)

            # Also try table extraction (narratives sometimes have tables)
            try:
                result.tables = extract_tables(file_path)
            except Exception:
                pass

        elif result.category == DocumentCategory.PROCEDURAL:
            logger.info(f"Skipping procedural document: {file_path.name}")
            result.status = "skipped"
            return result

        result.status = "parsed"

    except Exception as e:
        result.errors.append(f"Parsing failed: {e}")
        result.status = "failed"
        logger.error(f"Parsing failed for {file_path.name}: {e}")
        return result

    # Step 4: Auto-detect table types
    for table in result.tables:
        detected = detect_table_type(table.df)
        if detected:
            table.title = table.title or detected
            logger.info(f"Detected table type: {detected} ({len(table.df)} rows)")

    # Step 5: LLM extraction (if requested)
    if run_llm and text:
        extraction_types = llm_extraction_types or _auto_detect_extraction_types(
            result.tables, text, filing_type
        )

        for etype in extraction_types:
            logger.info(f"Running LLM extraction: {etype}")
            try:
                extracted = extract_with_llm(
                    text=text,
                    extraction_type=etype,
                    utility_name=utility_name,
                )
                if extracted:
                    result.extractions.append(extracted)
            except Exception as e:
                result.errors.append(f"LLM extraction ({etype}) failed: {e}")

        if result.extractions:
            result.status = "extracted"

    return result


def _auto_detect_extraction_types(
    tables: list[ParsedTable],
    text: str,
    filing_type: Optional[str] = None,
) -> list[str]:
    """Auto-detect which extraction types to run based on content."""
    types = set()

    # From table types
    for table in tables:
        if table.title:
            types.add(table.title)

    # From filing type
    filing_map = {
        "IRP": ["load_forecast", "resource_need"],
        "DRP": ["grid_constraint", "hosting_capacity"],
        "GNA": ["grid_constraint"],
        "rate_case": ["load_forecast"],
        "hosting_capacity": ["hosting_capacity"],
    }
    if filing_type and filing_type in filing_map:
        types.update(filing_map[filing_type])

    # From text keywords
    text_lower = text[:5000].lower()
    if "load forecast" in text_lower or "peak demand" in text_lower:
        types.add("load_forecast")
    if "constraint" in text_lower or "overload" in text_lower:
        types.add("grid_constraint")
    if "resource need" in text_lower or "procurement" in text_lower:
        types.add("resource_need")
    if "hosting capacity" in text_lower or "integration capacity" in text_lower:
        types.add("hosting_capacity")

    # Always start with general summary if no specific type detected
    if not types:
        types.add("general_summary")

    return list(types)
