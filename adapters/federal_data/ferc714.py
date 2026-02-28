"""FERC Form 714 annual load data parser.

FERC Form 714 requires large electric utilities and balancing authorities to
report hourly load data, planning area descriptions, and adjacent systems.

Data is available from:
  - FERC eLibrary (individual filings)
  - FERC bulk data download (all respondents, current + historical)
  - Catalyst Cooperative PUDL (cleaned/integrated, recommended)

The PUDL-cleaned version is strongly preferred as it normalizes respondent IDs,
fills gaps, and integrates with EIA utility IDs.
"""

import csv
import io
import logging
import zipfile
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Optional

import requests

logger = logging.getLogger(__name__)

# FERC Form 714 bulk data (all respondents)
FERC714_BULK_URL = "https://eforms.ferc.gov/eFormServer/EFormService/download/714"

# PUDL data releases (cleaned, integrated FERC 714 + EIA data)
PUDL_RELEASES_URL = "https://data.catalyst.coop"
PUDL_GITHUB = "https://github.com/catalyst-cooperative/pudl"


@dataclass
class Form714Respondent:
    """A FERC Form 714 respondent (planning area / balancing authority)."""
    respondent_id: int
    respondent_name: str
    eia_code: Optional[int] = None
    state: Optional[str] = None
    respondent_type: Optional[str] = None  # utility, ba, rto


@dataclass
class Form714HourlyLoad:
    """Hourly load data from FERC Form 714."""
    respondent_id: int
    report_year: int
    report_date: date
    hour: int  # 0-23
    load_mw: float


@dataclass
class Form714PlanningArea:
    """Planning area description from FERC Form 714."""
    respondent_id: int
    respondent_name: str
    report_year: int
    peak_demand_mw: Optional[float] = None
    annual_energy_gwh: Optional[float] = None
    summer_peak_mw: Optional[float] = None
    winter_peak_mw: Optional[float] = None
    adjacent_systems: list[str] = field(default_factory=list)


class FERC714Parser:
    """Parser for FERC Form 714 bulk data files."""

    def __init__(self, data_dir: Optional[Path] = None):
        self.data_dir = data_dir or Path("data/ferc714")
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "grid-constraint-classifier/2.0 (research)",
        })

    def download_bulk_data(self, dest_dir: Optional[Path] = None) -> Optional[Path]:
        """Download FERC Form 714 bulk data ZIP file."""
        dest_dir = dest_dir or self.data_dir
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_path = dest_dir / "ferc714_bulk.zip"

        if dest_path.exists():
            logger.info(f"Bulk data already downloaded: {dest_path}")
            return dest_path

        logger.info("Downloading FERC Form 714 bulk data...")
        try:
            resp = self.session.get(FERC714_BULK_URL, timeout=300, stream=True)
            resp.raise_for_status()
            with open(dest_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)
            logger.info(f"Saved to {dest_path} ({dest_path.stat().st_size:,} bytes)")
            return dest_path
        except Exception as e:
            logger.error(f"Download failed: {e}")
            return None

    def parse_respondents(self, zip_path: Path) -> list[Form714Respondent]:
        """Parse respondent list from Form 714 ZIP file."""
        respondents = []

        try:
            with zipfile.ZipFile(zip_path) as zf:
                # Look for respondent file (naming varies by year)
                respondent_files = [
                    n for n in zf.namelist()
                    if "respondent" in n.lower() and n.endswith(".csv")
                ]
                if not respondent_files:
                    logger.warning("No respondent CSV found in ZIP")
                    return []

                with zf.open(respondent_files[0]) as f:
                    reader = csv.DictReader(io.TextIOWrapper(f, encoding="utf-8"))
                    for row in reader:
                        resp = Form714Respondent(
                            respondent_id=int(row.get("respondent_id", row.get("RespondentID", 0))),
                            respondent_name=row.get("respondent_name", row.get("RespondentName", "")),
                            eia_code=_safe_int(row.get("eia_code", row.get("EIACode"))),
                            state=row.get("state", row.get("State")),
                        )
                        respondents.append(resp)

                logger.info(f"Parsed {len(respondents)} respondents")

        except Exception as e:
            logger.error(f"Failed to parse respondents: {e}")

        return respondents

    def parse_planning_areas(
        self,
        zip_path: Path,
        year: Optional[int] = None,
    ) -> list[Form714PlanningArea]:
        """Parse planning area data from Form 714 ZIP file."""
        areas = []

        try:
            with zipfile.ZipFile(zip_path) as zf:
                # Look for planning area / demand file
                area_files = [
                    n for n in zf.namelist()
                    if ("planning" in n.lower() or "demand" in n.lower() or "part2" in n.lower())
                    and n.endswith(".csv")
                ]
                if not area_files:
                    logger.warning("No planning area CSV found in ZIP")
                    return []

                with zf.open(area_files[0]) as f:
                    reader = csv.DictReader(io.TextIOWrapper(f, encoding="utf-8"))
                    for row in reader:
                        report_year = _safe_int(row.get("report_year", row.get("ReportYear")))
                        if year and report_year != year:
                            continue

                        area = Form714PlanningArea(
                            respondent_id=int(row.get("respondent_id", row.get("RespondentID", 0))),
                            respondent_name=row.get("respondent_name", row.get("RespondentName", "")),
                            report_year=report_year or 0,
                            peak_demand_mw=_safe_float(row.get("peak_demand_mw", row.get("PeakDemandMW"))),
                            annual_energy_gwh=_safe_float(row.get("net_energy_gwh", row.get("NetEnergyGWh"))),
                            summer_peak_mw=_safe_float(row.get("summer_peak_mw", row.get("SummerPeakMW"))),
                            winter_peak_mw=_safe_float(row.get("winter_peak_mw", row.get("WinterPeakMW"))),
                        )
                        areas.append(area)

                logger.info(f"Parsed {len(areas)} planning area records")

        except Exception as e:
            logger.error(f"Failed to parse planning areas: {e}")

        return areas

    def parse_hourly_loads(
        self,
        zip_path: Path,
        respondent_id: Optional[int] = None,
        year: Optional[int] = None,
        limit: Optional[int] = None,
    ) -> list[Form714HourlyLoad]:
        """Parse hourly load data from Form 714 ZIP file.

        Warning: This can be very large (millions of rows). Use filters.
        """
        loads = []

        try:
            with zipfile.ZipFile(zip_path) as zf:
                hourly_files = [
                    n for n in zf.namelist()
                    if ("hourly" in n.lower() or "part3" in n.lower())
                    and n.endswith(".csv")
                ]
                if not hourly_files:
                    logger.warning("No hourly load CSV found in ZIP")
                    return []

                with zf.open(hourly_files[0]) as f:
                    reader = csv.DictReader(io.TextIOWrapper(f, encoding="utf-8"))
                    for row in reader:
                        rid = int(row.get("respondent_id", row.get("RespondentID", 0)))
                        if respondent_id and rid != respondent_id:
                            continue

                        ryear = _safe_int(row.get("report_year", row.get("Year")))
                        if year and ryear != year:
                            continue

                        # Parse date and hour
                        date_str = row.get("plan_date", row.get("PlanDate", row.get("date", "")))
                        hour = _safe_int(row.get("hour", row.get("Hour"))) or 0
                        load_val = _safe_float(row.get("load_mw", row.get("LoadMW")))

                        if not date_str or load_val is None:
                            continue

                        try:
                            from datetime import datetime
                            dt = datetime.strptime(date_str[:10], "%Y-%m-%d").date()
                        except (ValueError, TypeError):
                            try:
                                from datetime import datetime
                                dt = datetime.strptime(date_str[:10], "%m/%d/%Y").date()
                            except (ValueError, TypeError):
                                continue

                        loads.append(Form714HourlyLoad(
                            respondent_id=rid,
                            report_year=ryear or dt.year,
                            report_date=dt,
                            hour=hour,
                            load_mw=load_val,
                        ))

                        if limit and len(loads) >= limit:
                            break

                logger.info(f"Parsed {len(loads)} hourly load records")

        except Exception as e:
            logger.error(f"Failed to parse hourly loads: {e}")

        return loads

    def __repr__(self) -> str:
        return f"<FERC714Parser(data_dir={self.data_dir})>"


def _safe_int(val) -> Optional[int]:
    """Safely convert to int."""
    if val is None or val == "":
        return None
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return None


def _safe_float(val) -> Optional[float]:
    """Safely convert to float."""
    if val is None or val == "":
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None
