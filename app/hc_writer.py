"""
Hosting capacity DB writer.

Follows PipelineWriter patterns: lazy DB session, batch insert,
ingestion run lifecycle tracking, and summary computation.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

import pandas as pd
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import (
    ISO, Utility, HCIngestionRun,
    HostingCapacityRecord, HostingCapacitySummary,
)
from adapters.hosting_capacity.base import UtilityHCConfig

logger = logging.getLogger(__name__)


class HostingCapacityWriter:
    """Writes hosting capacity data to the database."""

    def __init__(self):
        self._db: Optional[Session] = None

    @property
    def db(self) -> Session:
        if self._db is None:
            self._db = SessionLocal()
        return self._db

    def close(self):
        if self._db:
            self._db.close()
            self._db = None

    def ensure_utility(self, config: UtilityHCConfig) -> Utility:
        """Get or create a utility record from adapter config."""
        util = (
            self.db.query(Utility)
            .filter(Utility.utility_code == config.utility_code)
            .first()
        )
        if not util:
            iso = (
                self.db.query(ISO)
                .filter(ISO.iso_code == config.iso_id)
                .first()
            )
            util = Utility(
                utility_code=config.utility_code,
                utility_name=config.utility_name,
                parent_company=config.parent_company,
                iso_id=iso.id if iso else None,
                states=config.states,
                data_source_type=config.data_source_type,
                requires_auth=config.requires_auth,
                service_url=config.service_url,
            )
            self.db.add(util)
            self.db.flush()
            logger.info(f"Created utility record: {config.utility_code}")
        return util

    def get_last_hash(self, utility_id: int) -> Optional[str]:
        """Return source_hash from the latest completed ingestion run for this utility."""
        run = (
            self.db.query(HCIngestionRun)
            .filter(
                HCIngestionRun.utility_id == utility_id,
                HCIngestionRun.status == "completed",
            )
            .order_by(HCIngestionRun.completed_at.desc())
            .first()
        )
        return run.source_hash if run else None

    def start_run(self, utility: Utility, source_url: str) -> HCIngestionRun:
        """Create an ingestion run record."""
        run = HCIngestionRun(
            utility_id=utility.id,
            started_at=datetime.now(timezone.utc),
            status="running",
            source_url=source_url,
        )
        self.db.add(run)
        self.db.commit()
        logger.info(f"Started ingestion run #{run.id} for {utility.utility_code}")
        return run

    def write_records(
        self,
        df: pd.DataFrame,
        utility: Utility,
        run: HCIngestionRun,
        batch_size: int = 5000,
    ) -> int:
        """Batch-insert hosting capacity records using SQLAlchemy Core.

        Uses latest-wins strategy: clears previous records for this utility
        before inserting the new batch. Core insert avoids ORM object
        instantiation overhead for 2M+ records.
        """
        table = HostingCapacityRecord.__table__

        # Clear previous records for this utility (latest-wins) via Core
        result = self.db.execute(
            table.delete().where(
                table.c.utility_id == utility.id,
                table.c.ingestion_run_id != run.id,
            )
        )
        if result.rowcount:
            logger.info(f"Cleared {result.rowcount} previous HC records for {utility.utility_code}")
        self.db.commit()

        # Build record dicts from DataFrame
        records = []
        for _, row in df.iterrows():
            records.append({
                "utility_id": utility.id,
                "ingestion_run_id": run.id,
                "feeder_id_external": row["feeder_id_external"],
                "feeder_name": _safe_str(row.get("feeder_name")),
                "substation_name": _safe_str(row.get("substation_name")),
                "hosting_capacity_mw": _safe_float(row.get("hosting_capacity_mw")),
                "hosting_capacity_min_mw": _safe_float(row.get("hosting_capacity_min_mw")),
                "hosting_capacity_max_mw": _safe_float(row.get("hosting_capacity_max_mw")),
                "installed_dg_mw": _safe_float(row.get("installed_dg_mw")),
                "queued_dg_mw": _safe_float(row.get("queued_dg_mw")),
                "remaining_capacity_mw": _safe_float(row.get("remaining_capacity_mw")),
                "constraining_metric": row.get("constraining_metric"),
                "voltage_kv": _safe_float(row.get("voltage_kv")),
                "phase_config": row.get("phase_config"),
                "is_overhead": _safe_bool(row.get("is_overhead")),
                "is_network": _safe_bool(row.get("is_network")),
                "centroid_lat": _safe_float(row.get("centroid_lat")),
                "centroid_lon": _safe_float(row.get("centroid_lon")),
                "geometry_json": row.get("geometry_json"),
                "raw_attributes": row.get("raw_attributes"),
            })

        # Batch insert using Core (no ORM object instantiation)
        count = len(records)
        for i in range(0, count, batch_size):
            batch = records[i:i + batch_size]
            self.db.execute(table.insert(), batch)
            self.db.commit()
            logger.debug(f"  Wrote batch of {len(batch)} records ({i + len(batch)}/{count})")

        run.records_written = count
        utility.last_ingested_at = datetime.now(timezone.utc)
        self.db.commit()

        return count

    def compute_summary(self, utility: Utility):
        """Compute and upsert HostingCapacitySummary for a utility."""
        records = (
            self.db.query(HostingCapacityRecord)
            .filter(HostingCapacityRecord.utility_id == utility.id)
            .all()
        )

        total_hc = sum(r.hosting_capacity_mw or 0 for r in records)
        total_dg = sum(r.installed_dg_mw or 0 for r in records)
        total_remaining = sum(r.remaining_capacity_mw or 0 for r in records)
        constrained = sum(
            1 for r in records
            if (r.remaining_capacity_mw or float("inf")) < 1.0
        )

        # Utilization: installed / capacity
        utilization_pcts = []
        for r in records:
            if r.hosting_capacity_mw and r.hosting_capacity_mw > 0:
                installed = r.installed_dg_mw or 0
                utilization_pcts.append(installed / r.hosting_capacity_mw * 100)
        avg_util = (
            sum(utilization_pcts) / len(utilization_pcts)
            if utilization_pcts
            else None
        )

        # Constraint breakdown
        breakdown: dict[str, int] = {}
        for r in records:
            if r.constraining_metric:
                breakdown[r.constraining_metric] = (
                    breakdown.get(r.constraining_metric, 0) + 1
                )

        summary = (
            self.db.query(HostingCapacitySummary)
            .filter(HostingCapacitySummary.utility_id == utility.id)
            .first()
        )
        if not summary:
            summary = HostingCapacitySummary(utility_id=utility.id)
            self.db.add(summary)

        summary.total_feeders = len(records)
        summary.total_hosting_capacity_mw = round(total_hc, 2)
        summary.total_installed_dg_mw = round(total_dg, 2)
        summary.total_remaining_capacity_mw = round(total_remaining, 2)
        summary.avg_utilization_pct = round(avg_util, 1) if avg_util else None
        summary.constrained_feeders_count = constrained
        summary.constraint_breakdown = breakdown
        summary.computed_at = datetime.now(timezone.utc)

        self.db.commit()
        logger.info(
            f"Summary for {utility.utility_code}: {len(records)} feeders, "
            f"{round(total_hc, 1)} MW total HC, {constrained} constrained"
        )

    def complete_run(
        self, run: HCIngestionRun, error: Optional[str] = None,
    ):
        """Mark ingestion run as completed or failed."""
        try:
            self.db.rollback()  # Clear any pending failed transaction
        except Exception:
            pass
        run.completed_at = datetime.now(timezone.utc)
        run.status = "failed" if error else "completed"
        if error:
            run.error_message = str(error)[:1000]
        self.db.commit()
        logger.info(f"Ingestion run #{run.id} -> {run.status}")


def _safe_str(val) -> Optional[str]:
    """Convert to string, returning None for NaN/None/'None'."""
    if val is None:
        return None
    if isinstance(val, float) and val != val:  # NaN
        return None
    s = str(val)
    return None if s in ("None", "nan", "") else s


def _safe_float(val) -> Optional[float]:
    """Convert to float, returning None for NaN/None/invalid."""
    if val is None:
        return None
    try:
        f = float(val)
        if f != f:  # NaN check
            return None
        return f
    except (ValueError, TypeError):
        return None


def _safe_bool(val) -> Optional[bool]:
    """Convert to bool, returning None for non-boolean values."""
    if val is None:
        return None
    if isinstance(val, bool):
        return val
    if isinstance(val, (int, float)):
        if val != val:  # NaN
            return None
        return bool(val)
    if isinstance(val, str):
        if val.lower() in ("true", "yes", "1", "y"):
            return True
        if val.lower() in ("false", "no", "0", "n"):
            return False
    return None
