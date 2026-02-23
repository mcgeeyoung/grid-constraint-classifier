"""
Pipeline DB writer: persists pipeline results to PostgreSQL.

Called by cli/run_pipeline.py after each phase to write classification
results, pnode scores, data centers, and DER recommendations to the DB.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

import pandas as pd
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import (
    ISO, Zone, ZoneLMP, PipelineRun,
    ZoneClassification, Pnode, PnodeScore,
    DataCenter, DERRecommendation,
)

logger = logging.getLogger(__name__)


class PipelineWriter:
    """Writes pipeline results to the database."""

    def __init__(self, iso_id: str, iso_name: str, iso_config: dict):
        self.iso_id = iso_id
        self.iso_name = iso_name
        self.iso_config = iso_config
        self._db: Optional[Session] = None
        self._iso: Optional[ISO] = None
        self._run: Optional[PipelineRun] = None
        self._zone_lookup: dict[str, Zone] = {}

    @property
    def db(self) -> Session:
        if self._db is None:
            self._db = SessionLocal()
        return self._db

    def close(self):
        if self._db:
            self._db.close()
            self._db = None

    def start_run(self, year: int) -> int:
        """Create a pipeline run record and return its ID."""
        try:
            self._ensure_iso_and_zones()

            self._run = PipelineRun(
                iso_id=self._iso.id,
                year=year,
                started_at=datetime.now(timezone.utc),
                status="running",
            )
            self.db.add(self._run)
            self.db.commit()
            logger.info(f"DB: Created pipeline run #{self._run.id}")
            return self._run.id
        except Exception as e:
            logger.warning(f"DB write failed (start_run): {e}")
            self.db.rollback()
            return -1

    def _ensure_iso_and_zones(self):
        """Ensure the ISO and zone records exist."""
        self._iso = self.db.query(ISO).filter(ISO.iso_code == self.iso_id).first()
        if not self._iso:
            self._iso = ISO(
                iso_code=self.iso_id,
                iso_name=self.iso_name,
                timezone=self.iso_config.get("timezone", "US/Eastern"),
                has_decomposition=self.iso_config.get("has_lmp_decomposition", True),
                has_node_pricing=self.iso_config.get("has_node_level_pricing", True),
            )
            self.db.add(self._iso)
            self.db.flush()

        zones = self.iso_config.get("zones", {})
        for code, zinfo in zones.items():
            zone = self.db.query(Zone).filter(
                Zone.iso_id == self._iso.id, Zone.zone_code == code
            ).first()
            if not zone:
                zone = Zone(
                    iso_id=self._iso.id,
                    zone_code=code,
                    zone_name=zinfo.get("name", code),
                    centroid_lat=zinfo.get("centroid_lat"),
                    centroid_lon=zinfo.get("centroid_lon"),
                    states=zinfo.get("states", []),
                )
                self.db.add(zone)
                self.db.flush()
            self._zone_lookup[code] = zone

        self.db.commit()

    def write_zone_lmp_count(self, count: int):
        """Update the pipeline run with zone LMP row count."""
        if not self._run:
            return
        try:
            self._run.zone_lmp_rows = count
            self.db.commit()
        except Exception as e:
            logger.warning(f"DB write failed (zone_lmp_count): {e}")
            self.db.rollback()

    def write_classifications(self, classification_df: pd.DataFrame):
        """Write zone classification results."""
        if not self._run:
            return
        try:
            count = 0
            for _, row in classification_df.iterrows():
                zone = self._zone_lookup.get(row["zone"])
                if not zone:
                    continue

                cls = ZoneClassification(
                    pipeline_run_id=self._run.id,
                    zone_id=zone.id,
                    classification=row["classification"],
                    transmission_score=row["transmission_score"],
                    generation_score=row["generation_score"],
                    avg_abs_congestion=row.get("avg_abs_congestion"),
                    max_congestion=row.get("max_congestion"),
                    congested_hours_pct=row.get("congested_hours_pct"),
                )
                self.db.add(cls)
                count += 1

            self.db.commit()
            logger.info(f"DB: Wrote {count} zone classifications")
        except Exception as e:
            logger.warning(f"DB write failed (classifications): {e}")
            self.db.rollback()

    def write_pnode_scores(self, pnode_results: dict):
        """Write pnode severity scores."""
        if not self._run or not pnode_results:
            return
        try:
            count = 0
            for zone_code, analysis in pnode_results.items():
                zone = self._zone_lookup.get(zone_code)
                if not zone:
                    continue

                for pdata in analysis.get("all_scored", []):
                    ext_id = str(pdata.get("pnode_id", pdata["pnode_name"]))

                    pnode = self.db.query(Pnode).filter(
                        Pnode.iso_id == self._iso.id,
                        Pnode.node_id_external == ext_id,
                    ).first()
                    if not pnode:
                        pnode = Pnode(
                            iso_id=self._iso.id,
                            zone_id=zone.id,
                            node_id_external=ext_id,
                            node_name=pdata["pnode_name"],
                        )
                        self.db.add(pnode)
                        self.db.flush()

                    score = PnodeScore(
                        pipeline_run_id=self._run.id,
                        pnode_id=pnode.id,
                        severity_score=pdata["severity_score"],
                        tier=pdata["tier"],
                        avg_congestion=pdata.get("avg_congestion"),
                        max_congestion=pdata.get("max_congestion"),
                        congested_hours_pct=pdata.get("congested_hours_pct"),
                        constraint_loadshape=pdata.get("constraint_loadshape"),
                    )
                    self.db.add(score)
                    count += 1

            self.db.commit()
            logger.info(f"DB: Wrote {count} pnode scores")
        except Exception as e:
            logger.warning(f"DB write failed (pnode_scores): {e}")
            self.db.rollback()

    def write_recommendations(self, recommendations: list[dict]):
        """Write DER recommendations."""
        if not self._run or not recommendations:
            return
        try:
            count = 0
            for rec in recommendations:
                zone = self._zone_lookup.get(rec.get("zone"))
                if not zone:
                    continue

                der_rec = DERRecommendation(
                    pipeline_run_id=self._run.id,
                    zone_id=zone.id,
                    classification=rec.get("classification"),
                    rationale=rec.get("rationale"),
                    congestion_value=rec.get("congestion_value_annual"),
                    primary_rec=rec.get("primary_recommendation"),
                    secondary_rec=rec.get("secondary_recommendation"),
                    tertiary_rec=rec.get("tertiary_recommendation"),
                )
                self.db.add(der_rec)
                count += 1

            self.db.commit()
            logger.info(f"DB: Wrote {count} DER recommendations")
        except Exception as e:
            logger.warning(f"DB write failed (recommendations): {e}")
            self.db.rollback()

    def complete_run(self, error: Optional[str] = None):
        """Mark the pipeline run as completed or failed."""
        if not self._run:
            return
        try:
            self._run.completed_at = datetime.now(timezone.utc)
            self._run.status = "failed" if error else "completed"
            if error:
                self._run.error_message = str(error)[:1000]
            self.db.commit()
            logger.info(f"DB: Pipeline run #{self._run.id} -> {self._run.status}")
        except Exception as e:
            logger.warning(f"DB write failed (complete_run): {e}")
            self.db.rollback()


def get_pipeline_writer(iso_id: str, adapter) -> Optional[PipelineWriter]:
    """
    Create a PipelineWriter if a database is available.

    Returns None if the database is not configured or unreachable,
    allowing the pipeline to run file-only.
    """
    try:
        from app.config import settings
        # Quick test: can we connect?
        from sqlalchemy import create_engine, text
        test_engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)
        with test_engine.connect() as conn:
            conn.execute(text("SELECT 1"))

        config = adapter.config
        return PipelineWriter(
            iso_id=iso_id,
            iso_name=config.iso_name,
            iso_config={
                "timezone": config.timezone,
                "has_lmp_decomposition": config.has_lmp_decomposition,
                "has_node_level_pricing": config.has_node_level_pricing,
                "zones": config.zones,
            },
        )
    except Exception as e:
        logger.debug(f"Database not available, running file-only: {e}")
        return None
