"""PDF text and table extraction.

Uses multiple extraction strategies with fallback:
  1. pdfplumber for text extraction (reliable, pure Python)
  2. tabula-py for table extraction (Java-based, good for structured tables)
  3. pdfplumber table detection as fallback
"""

import logging
from pathlib import Path
from typing import Optional

import pandas as pd

from .base import Confidence, ParsedTable

logger = logging.getLogger(__name__)


def extract_text(pdf_path: Path, max_pages: Optional[int] = None) -> tuple[str, int]:
    """Extract text from a PDF file.

    Returns (text, page_count).
    """
    try:
        import pdfplumber
    except ImportError:
        logger.warning("pdfplumber not installed, trying PyPDF2 fallback")
        return _extract_text_pypdf2(pdf_path, max_pages)

    text_parts = []
    page_count = 0

    try:
        with pdfplumber.open(str(pdf_path)) as pdf:
            page_count = len(pdf.pages)
            limit = min(page_count, max_pages) if max_pages else page_count

            for i, page in enumerate(pdf.pages[:limit]):
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(f"--- Page {i + 1} ---\n{page_text}")

    except Exception as e:
        logger.error(f"pdfplumber failed on {pdf_path.name}: {e}")
        return _extract_text_pypdf2(pdf_path, max_pages)

    return "\n\n".join(text_parts), page_count


def _extract_text_pypdf2(pdf_path: Path, max_pages: Optional[int] = None) -> tuple[str, int]:
    """Fallback text extraction using PyPDF2."""
    try:
        from PyPDF2 import PdfReader
    except ImportError:
        logger.error("Neither pdfplumber nor PyPDF2 available")
        return "", 0

    text_parts = []
    try:
        reader = PdfReader(str(pdf_path))
        page_count = len(reader.pages)
        limit = min(page_count, max_pages) if max_pages else page_count

        for i in range(limit):
            page_text = reader.pages[i].extract_text()
            if page_text:
                text_parts.append(f"--- Page {i + 1} ---\n{page_text}")

    except Exception as e:
        logger.error(f"PyPDF2 failed on {pdf_path.name}: {e}")
        return "", 0

    return "\n\n".join(text_parts), page_count


def extract_tables(pdf_path: Path, pages: str = "all") -> list[ParsedTable]:
    """Extract tables from a PDF using tabula-py with pdfplumber fallback.

    Args:
        pdf_path: Path to the PDF file.
        pages: Page specification for tabula ("all", "1-5", "1,3,5").

    Returns:
        List of ParsedTable objects.
    """
    tables = []

    # Try tabula-py first (best for well-structured tables)
    try:
        tables = _extract_tables_tabula(pdf_path, pages)
        if tables:
            logger.info(f"tabula extracted {len(tables)} tables from {pdf_path.name}")
            return tables
    except Exception as e:
        logger.debug(f"tabula failed on {pdf_path.name}: {e}")

    # Fallback to pdfplumber
    try:
        tables = _extract_tables_pdfplumber(pdf_path)
        if tables:
            logger.info(f"pdfplumber extracted {len(tables)} tables from {pdf_path.name}")
            return tables
    except Exception as e:
        logger.debug(f"pdfplumber table extraction failed on {pdf_path.name}: {e}")

    return tables


def _extract_tables_tabula(pdf_path: Path, pages: str = "all") -> list[ParsedTable]:
    """Extract tables using tabula-py."""
    import tabula

    results = []

    # Try lattice mode first (bordered tables)
    try:
        dfs = tabula.read_pdf(
            str(pdf_path),
            pages=pages,
            lattice=True,
            multiple_tables=True,
            silent=True,
        )
        for i, df in enumerate(dfs):
            if _is_valid_table(df):
                results.append(ParsedTable(
                    df=df,
                    table_index=i,
                    confidence=Confidence.HIGH,
                    source_method="tabula_lattice",
                ))
    except Exception:
        pass

    # If no lattice tables found, try stream mode (unbordered)
    if not results:
        try:
            dfs = tabula.read_pdf(
                str(pdf_path),
                pages=pages,
                stream=True,
                multiple_tables=True,
                silent=True,
            )
            for i, df in enumerate(dfs):
                if _is_valid_table(df):
                    results.append(ParsedTable(
                        df=df,
                        table_index=i,
                        confidence=Confidence.MEDIUM,
                        source_method="tabula_stream",
                    ))
        except Exception:
            pass

    return results


def _extract_tables_pdfplumber(pdf_path: Path) -> list[ParsedTable]:
    """Extract tables using pdfplumber."""
    import pdfplumber

    results = []
    table_idx = 0

    with pdfplumber.open(str(pdf_path)) as pdf:
        for page_num, page in enumerate(pdf.pages, 1):
            page_tables = page.extract_tables()
            if not page_tables:
                continue

            for table in page_tables:
                if not table or len(table) < 2:
                    continue

                # Convert to DataFrame
                # First row is typically the header
                header = [str(c).strip() if c else f"col_{j}"
                          for j, c in enumerate(table[0])]
                rows = table[1:]

                try:
                    df = pd.DataFrame(rows, columns=header)
                    if _is_valid_table(df):
                        results.append(ParsedTable(
                            df=df,
                            page_number=page_num,
                            table_index=table_idx,
                            confidence=Confidence.MEDIUM,
                            source_method="pdfplumber",
                        ))
                        table_idx += 1
                except Exception as e:
                    logger.debug(f"Failed to create DataFrame from table on page {page_num}: {e}")

    return results


def _is_valid_table(df: pd.DataFrame) -> bool:
    """Check if an extracted DataFrame looks like a real table."""
    if df.empty:
        return False
    if len(df) < 2:  # Need at least 2 data rows
        return False
    if len(df.columns) < 2:  # Need at least 2 columns
        return False

    # Check that it's not all NaN
    non_null_pct = df.notna().sum().sum() / (len(df) * len(df.columns))
    if non_null_pct < 0.3:
        return False

    return True
