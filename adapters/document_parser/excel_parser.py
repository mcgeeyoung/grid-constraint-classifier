"""Excel and CSV table parsing.

Handles structured data files from utility filings:
  - Load forecast spreadsheets
  - Hosting capacity data exports
  - Grid needs assessment data
  - Rate schedule tables
"""

import logging
from pathlib import Path
from typing import Optional

import pandas as pd

from .base import Confidence, ParsedTable

logger = logging.getLogger(__name__)


def parse_excel(
    file_path: Path,
    sheet_name: Optional[str] = None,
    max_sheets: int = 10,
) -> list[ParsedTable]:
    """Parse an Excel file into ParsedTable objects.

    Reads all sheets (up to max_sheets) and returns non-empty tables.
    """
    suffix = file_path.suffix.lower()
    results = []

    if suffix == ".csv":
        return _parse_csv(file_path)

    if suffix == ".tsv":
        return _parse_csv(file_path, sep="\t")

    try:
        xls = pd.ExcelFile(file_path)
    except Exception as e:
        logger.error(f"Failed to open {file_path.name}: {e}")
        return []

    sheets = [sheet_name] if sheet_name else xls.sheet_names[:max_sheets]

    for i, sheet in enumerate(sheets):
        try:
            df = pd.read_excel(xls, sheet_name=sheet)

            # Skip empty or header-only sheets
            if df.empty or len(df) < 1:
                continue

            # Clean up: drop fully empty rows and columns
            df = df.dropna(how="all").dropna(axis=1, how="all")
            if df.empty:
                continue

            results.append(ParsedTable(
                df=df,
                table_index=i,
                title=sheet,
                confidence=Confidence.HIGH,
                source_method="openpyxl",
            ))

        except Exception as e:
            logger.warning(f"Failed to read sheet '{sheet}' from {file_path.name}: {e}")

    logger.info(f"Parsed {len(results)} sheets from {file_path.name}")
    return results


def _parse_csv(file_path: Path, sep: str = ",") -> list[ParsedTable]:
    """Parse a CSV/TSV file."""
    try:
        df = pd.read_csv(file_path, sep=sep)
        df = df.dropna(how="all").dropna(axis=1, how="all")

        if df.empty:
            return []

        return [ParsedTable(
            df=df,
            table_index=0,
            title=file_path.stem,
            confidence=Confidence.HIGH,
            source_method="pandas_csv",
        )]
    except Exception as e:
        logger.error(f"Failed to parse {file_path.name}: {e}")
        return []


def detect_table_type(df: pd.DataFrame) -> Optional[str]:
    """Attempt to classify what kind of data a table contains.

    Returns an extraction_type string or None if unrecognized.
    """
    cols_lower = [str(c).lower() for c in df.columns]
    all_cols = " ".join(cols_lower)

    # Load forecast indicators
    if any(kw in all_cols for kw in ("peak_demand", "peak demand", "energy_gwh", "forecast", "growth")):
        if any(kw in all_cols for kw in ("year", "mw", "gwh")):
            return "load_forecast"

    # Hosting capacity indicators
    if any(kw in all_cols for kw in ("hosting", "integration capacity", "feeder", "circuit")):
        if any(kw in all_cols for kw in ("mw", "kw", "capacity")):
            return "hosting_capacity"

    # Grid constraint indicators
    if any(kw in all_cols for kw in ("constraint", "overload", "thermal", "voltage limit")):
        return "grid_constraint"

    # Resource need indicators
    if any(kw in all_cols for kw in ("resource", "procurement", "need", "shortfall")):
        if any(kw in all_cols for kw in ("mw", "capacity")):
            return "resource_need"

    # Avoided cost indicators
    if any(kw in all_cols for kw in ("avoided cost", "marginal", "$/kwh", "$/mwh")):
        return "avoided_cost"

    return None
