"""Catalyst Cooperative PUDL (Public Utility Data Liberation) client.

PUDL is an open-source project that cleans and integrates EIA, FERC, and EPA
datasets into a unified, analysis-ready database. It is the recommended
starting point for federal utility data rather than reimplementing parsing.

PUDL data is available as:
  - SQLite database (pudl.sqlite, ~2GB)
  - Parquet files (individual tables)
  - Python package (catalystcoop.pudl)

Key tables:
  - core_eia861__yearly_service_territory: EIA-861 service territories
  - core_ferc714__respondent_id: FERC 714 respondent cross-ref
  - out_ferc714__hourly_estimated_state_demand: Hourly demand by state
  - core_eia__entity_utilities: Utility metadata
  - core_eia__entity_plants: Power plant metadata
  - out_eia860__yearly_generators: Generator data by year

Reference: https://catalystcoop.github.io/pudl/
"""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import requests

logger = logging.getLogger(__name__)

PUDL_NIGHTLY_URL = "https://data.catalyst.coop/pudl/nightly"
PUDL_STABLE_URL = "https://data.catalyst.coop/pudl"


@dataclass
class PUDLTable:
    """Metadata about a PUDL table."""
    name: str
    source: str  # eia, ferc, epa
    description: str
    row_count: Optional[int] = None
    parquet_url: Optional[str] = None


# Key PUDL tables for grid-constraint-classifier
PRIORITY_TABLES = [
    PUDLTable(
        name="core_eia861__yearly_service_territory",
        source="eia",
        description="Annual EIA-861 service territory (counties per utility per year).",
    ),
    PUDLTable(
        name="core_eia__entity_utilities",
        source="eia",
        description="Utility-level metadata: name, state, type, EIA ID.",
    ),
    PUDLTable(
        name="core_eia__entity_plants",
        source="eia",
        description="Power plant-level metadata: name, state, county, lat/lon.",
    ),
    PUDLTable(
        name="out_eia860__yearly_generators",
        source="eia",
        description="Generator data by year: capacity, fuel type, status, online date.",
    ),
    PUDLTable(
        name="core_ferc714__respondent_id",
        source="ferc",
        description="FERC 714 respondent IDs cross-referenced to EIA utility IDs.",
    ),
    PUDLTable(
        name="out_ferc714__hourly_estimated_state_demand",
        source="ferc",
        description="Hourly state-level demand estimates from FERC 714.",
    ),
    PUDLTable(
        name="core_eia861__yearly_utility_data_misc",
        source="eia",
        description="Annual utility-level data: customers, sales, revenue, sources.",
    ),
    PUDLTable(
        name="core_eia861__yearly_demand_side_management",
        source="eia",
        description="Utility DSM program data: energy savings, peak reduction.",
    ),
]


class PUDLClient:
    """Client for downloading and querying PUDL data."""

    def __init__(self, data_dir: Optional[Path] = None, use_nightly: bool = False):
        self.data_dir = data_dir or Path("data/pudl")
        self.base_url = PUDL_NIGHTLY_URL if use_nightly else PUDL_STABLE_URL
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "grid-constraint-classifier/2.0 (research)",
        })

    def download_sqlite(self) -> Optional[Path]:
        """Download the full PUDL SQLite database (~2GB)."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        dest = self.data_dir / "pudl.sqlite"

        if dest.exists():
            logger.info(f"PUDL SQLite already exists: {dest} ({dest.stat().st_size:,} bytes)")
            return dest

        url = f"{self.base_url}/pudl.sqlite"
        logger.info(f"Downloading PUDL SQLite from {url} (this may take a while)...")

        try:
            resp = self.session.get(url, timeout=600, stream=True)
            resp.raise_for_status()

            total = int(resp.headers.get("content-length", 0))
            downloaded = 0

            with open(dest, "wb") as f:
                for chunk in resp.iter_content(chunk_size=65536):
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total and downloaded % (50 * 1024 * 1024) == 0:
                        pct = (downloaded / total) * 100
                        logger.info(f"  {downloaded:,} / {total:,} bytes ({pct:.0f}%)")

            logger.info(f"Downloaded PUDL SQLite: {dest} ({dest.stat().st_size:,} bytes)")
            return dest

        except Exception as e:
            logger.error(f"PUDL download failed: {e}")
            if dest.exists():
                dest.unlink()
            return None

    def download_parquet(self, table_name: str) -> Optional[Path]:
        """Download a single PUDL table as Parquet file."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        dest = self.data_dir / f"{table_name}.parquet"

        if dest.exists():
            logger.info(f"Already downloaded: {dest}")
            return dest

        url = f"{self.base_url}/{table_name}.parquet"
        logger.info(f"Downloading {table_name}.parquet...")

        try:
            resp = self.session.get(url, timeout=300, stream=True)
            resp.raise_for_status()

            with open(dest, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)

            logger.info(f"Downloaded: {dest} ({dest.stat().st_size:,} bytes)")
            return dest

        except Exception as e:
            logger.error(f"Download failed for {table_name}: {e}")
            return None

    def query_sqlite(self, sql: str, db_path: Optional[Path] = None):
        """Run a SQL query against the PUDL SQLite database.

        Returns list of dicts. Requires sqlite3 (stdlib).
        """
        import sqlite3

        db = db_path or (self.data_dir / "pudl.sqlite")
        if not db.exists():
            logger.error(f"PUDL SQLite not found at {db}. Run download_sqlite() first.")
            return []

        conn = sqlite3.connect(str(db))
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(sql).fetchall()
            return [dict(r) for r in rows]
        except Exception as e:
            logger.error(f"Query failed: {e}")
            return []
        finally:
            conn.close()

    def get_utilities(self, state: Optional[str] = None, db_path: Optional[Path] = None) -> list[dict]:
        """Get utility list from PUDL with optional state filter."""
        sql = "SELECT * FROM core_eia__entity_utilities"
        if state:
            sql += f" WHERE state = '{state}'"
        return self.query_sqlite(sql, db_path)

    def get_plants(
        self,
        state: Optional[str] = None,
        utility_id: Optional[int] = None,
        db_path: Optional[Path] = None,
    ) -> list[dict]:
        """Get power plant list from PUDL."""
        sql = "SELECT * FROM core_eia__entity_plants WHERE 1=1"
        if state:
            sql += f" AND state = '{state}'"
        if utility_id:
            sql += f" AND utility_id_eia = {utility_id}"
        return self.query_sqlite(sql, db_path)

    def __repr__(self) -> str:
        return f"<PUDLClient(data_dir={self.data_dir})>"
