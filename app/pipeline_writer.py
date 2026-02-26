"""
Pipeline DB writer: persists pipeline results to PostgreSQL.

Called by cli/run_pipeline.py after each phase to write classification
results, pnode scores, data centers, and DER recommendations to the DB.
"""

import csv
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pandas as pd
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import (
    ISO, Zone, ZoneLMP, PipelineRun,
    ZoneClassification, Pnode, PnodeScore,
    DataCenter, DERRecommendation,
    TransmissionLine, Substation,
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

    def _get_or_create_zone(self, zone_code: str) -> Optional[Zone]:
        """Get or create a zone record for codes not in the adapter config."""
        if not zone_code or not self._iso:
            return None
        zone = self._zone_lookup.get(zone_code)
        if zone:
            return zone
        try:
            zone = self.db.query(Zone).filter(
                Zone.iso_id == self._iso.id, Zone.zone_code == zone_code
            ).first()
            if not zone:
                zone = Zone(
                    iso_id=self._iso.id,
                    zone_code=str(zone_code)[:50],
                    zone_name=str(zone_code)[:100],
                )
                self.db.add(zone)
                self.db.flush()
            self._zone_lookup[zone_code] = zone
            return zone
        except Exception:
            self.db.rollback()
            return None

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

    # ------------------------------------------------------------------
    # Zone LMP time-series
    # ------------------------------------------------------------------

    def _clear_zone_lmps(self):
        """Delete existing zone LMP rows for this ISO (allows clean re-runs)."""
        if not self._iso:
            return
        try:
            deleted = self.db.query(ZoneLMP).filter(
                ZoneLMP.iso_id == self._iso.id
            ).delete()
            self.db.commit()
            if deleted:
                logger.info(f"DB: Cleared {deleted} existing zone LMP rows")
        except Exception as e:
            logger.warning(f"DB clear zone_lmps failed: {e}")
            self.db.rollback()

    def write_zone_lmps(self, lmp_df: pd.DataFrame, batch_size: int = 5000):
        """
        Write zone-level LMP rows to the database.

        Expects a DataFrame with columns:
            zone, timestamp_utc, lmp, energy, congestion, loss,
            hour_local, month
        Skips rows for zones not in this ISO's zone_lookup.
        """
        if not self._iso:
            self._ensure_iso_and_zones()
        self._clear_zone_lmps()

        # Deduplicate on (zone, timestamp_utc) keeping first occurrence
        lmp_df = lmp_df.drop_duplicates(subset=["zone", "timestamp_utc"], keep="first")

        # Pre-create all zones before batch insertion
        for zone_code in lmp_df["zone"].unique():
            if zone_code not in self._zone_lookup:
                self._get_or_create_zone(zone_code)
        self.db.commit()

        try:
            count = 0
            batch: list[ZoneLMP] = []

            for _, row in lmp_df.iterrows():
                zone = self._zone_lookup.get(row["zone"])
                if not zone:
                    continue

                record = ZoneLMP(
                    iso_id=self._iso.id,
                    zone_id=zone.id,
                    timestamp_utc=row["timestamp_utc"],
                    lmp=row["lmp"],
                    energy=row.get("energy"),
                    congestion=row.get("congestion"),
                    loss=row.get("loss"),
                    hour_local=row["hour_local"],
                    month=row["month"],
                )
                batch.append(record)
                count += 1

                if len(batch) >= batch_size:
                    try:
                        self.db.bulk_save_objects(batch)
                        self.db.commit()
                    except Exception as batch_err:
                        logger.warning(f"DB batch failed, retrying row-by-row: {batch_err}")
                        self.db.rollback()
                        for obj in batch:
                            try:
                                self.db.add(obj)
                                self.db.flush()
                            except Exception:
                                self.db.rollback()
                        self.db.commit()
                    batch = []

            if batch:
                try:
                    self.db.bulk_save_objects(batch)
                    self.db.commit()
                except Exception:
                    self.db.rollback()
                    for obj in batch:
                        try:
                            self.db.add(obj)
                            self.db.flush()
                        except Exception:
                            self.db.rollback()
                    self.db.commit()

            logger.info(f"DB: Wrote {count} zone LMP rows")
            if self._run:
                self._run.zone_lmp_rows = count
                self.db.commit()
        except Exception as e:
            logger.warning(f"DB write failed (zone_lmps): {e}")
            self.db.rollback()

    # ------------------------------------------------------------------
    # Classifications (existing)
    # ------------------------------------------------------------------

    def write_classifications(self, classification_df: pd.DataFrame):
        """Write zone classification results."""
        if not self._run:
            return
        try:
            count = 0
            for _, row in classification_df.iterrows():
                zone = self._zone_lookup.get(row["zone"])
                if not zone:
                    zone = self._get_or_create_zone(row["zone"])
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

    # ------------------------------------------------------------------
    # Pnode scores (existing, now also writes coordinates)
    # ------------------------------------------------------------------

    def write_pnode_scores(self, pnode_results: dict, pnode_coordinates: Optional[dict] = None):
        """
        Write pnode severity scores.

        Args:
            pnode_results: {zone_code: {all_scored: [...]}} from pnode analyzer
            pnode_coordinates: optional {node_id: {lat, lon, source, matched_name}}
                loaded from data/{iso}/geo/pnode_coordinates.json
        """
        if not self._run or not pnode_results:
            return
        coords = pnode_coordinates or {}
        try:
            count = 0
            for zone_code, analysis in pnode_results.items():
                zone = self._zone_lookup.get(zone_code)
                # zone may be None for aggregate keys like PGE_ALL

                for pdata in analysis.get("all_scored", []):
                    ext_id = str(pdata.get("pnode_id", pdata["pnode_name"]))

                    pnode = self.db.query(Pnode).filter(
                        Pnode.iso_id == self._iso.id,
                        Pnode.node_id_external == ext_id,
                    ).first()
                    if not pnode:
                        coord = coords.get(pdata["pnode_name"], {})
                        pnode = Pnode(
                            iso_id=self._iso.id,
                            zone_id=zone.id if zone else None,
                            node_id_external=ext_id,
                            node_name=pdata["pnode_name"],
                            lat=coord.get("lat"),
                            lon=coord.get("lon"),
                        )
                        self.db.add(pnode)
                        self.db.flush()
                    elif not pnode.lat:
                        coord = coords.get(pdata["pnode_name"], {})
                        if coord.get("lat"):
                            pnode.lat = coord["lat"]
                            pnode.lon = coord.get("lon")

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

    # ------------------------------------------------------------------
    # Pnode coordinates (standalone backfill)
    # ------------------------------------------------------------------

    def write_pnode_coordinates(self, pnode_coordinates: dict):
        """
        Backfill lat/lon on existing Pnode records, or create stubs for
        pnodes that only exist in the coordinates file.

        Args:
            pnode_coordinates: {node_id: {lat, lon, source, matched_name}}
        """
        if not self._iso:
            self._ensure_iso_and_zones()
        try:
            updated = 0
            created = 0
            for ext_id, coord in pnode_coordinates.items():
                lat = coord.get("lat")
                lon = coord.get("lon")
                if lat is None or lon is None:
                    continue

                pnode = self.db.query(Pnode).filter(
                    Pnode.iso_id == self._iso.id,
                    Pnode.node_id_external == ext_id,
                ).first()

                if pnode:
                    if not pnode.lat:
                        pnode.lat = lat
                        pnode.lon = lon
                        updated += 1
                else:
                    pnode = Pnode(
                        iso_id=self._iso.id,
                        node_id_external=ext_id,
                        node_name=coord.get("matched_name") or ext_id,
                        lat=lat,
                        lon=lon,
                    )
                    self.db.add(pnode)
                    created += 1

            self.db.commit()
            logger.info(f"DB: Pnode coordinates — {updated} updated, {created} created")
        except Exception as e:
            logger.warning(f"DB write failed (pnode_coordinates): {e}")
            self.db.rollback()

    # ------------------------------------------------------------------
    # Data centers
    # ------------------------------------------------------------------

    def write_data_centers(self, dc_list: list[dict]):
        """
        Write data center records from dc_combined.json.

        Expects list of dicts with keys:
            slug, facility_name, county, state_code, status, capacity_mw,
            operator, iso_zone, lat (optional), lon (optional)
        """
        if not self._iso:
            self._ensure_iso_and_zones()
        try:
            count = 0
            for dc in dc_list:
                slug = dc.get("slug")
                if not slug:
                    continue

                existing = self.db.query(DataCenter).filter(
                    DataCenter.external_slug == slug
                ).first()
                if existing:
                    continue

                zone_code = dc.get("iso_zone")
                zone = self._zone_lookup.get(zone_code)

                record = DataCenter(
                    iso_id=self._iso.id,
                    zone_id=zone.id if zone else None,
                    external_slug=slug,
                    facility_name=dc.get("facility_name"),
                    status=dc.get("status"),
                    capacity_mw=dc.get("capacity_mw"),
                    lat=dc.get("lat"),
                    lon=dc.get("lon"),
                    state_code=dc.get("state_code"),
                    county=dc.get("county"),
                    operator=dc.get("operator"),
                    scraped_at=datetime.now(timezone.utc),
                )
                self.db.add(record)
                count += 1

            self.db.commit()
            logger.info(f"DB: Wrote {count} data centers")
        except Exception as e:
            logger.warning(f"DB write failed (data_centers): {e}")
            self.db.rollback()

    # ------------------------------------------------------------------
    # Zone boundaries (GeoJSON)
    # ------------------------------------------------------------------

    def write_zone_boundaries(self, geojson: dict):
        """
        Populate boundary_geojson on Zone records from a GeoJSON
        FeatureCollection.

        Expects features with properties.iso_zone matching zone_code.
        """
        if not self._iso:
            self._ensure_iso_and_zones()
        features = geojson.get("features", [])
        try:
            count = 0
            for feat in features:
                props = feat.get("properties", {})
                zone_code = props.get("iso_zone") or props.get("NAME")
                zone = self._zone_lookup.get(zone_code)
                if not zone:
                    continue

                zone.boundary_geojson = feat.get("geometry")
                count += 1

            self.db.commit()
            logger.info(f"DB: Wrote {count} zone boundaries")
        except Exception as e:
            logger.warning(f"DB write failed (zone_boundaries): {e}")
            self.db.rollback()

    # ------------------------------------------------------------------
    # Transmission lines (HIFLD GeoJSON)
    # ------------------------------------------------------------------

    def write_transmission_lines(self, geojson: dict, batch_size: int = 500):
        """
        Write transmission line features from HIFLD GeoJSON.

        Expects a FeatureCollection with LineString features having
        properties: VOLTAGE, OWNER, SUB_1, SUB_2, SHAPE__Len
        """
        if not self._iso:
            self._ensure_iso_and_zones()
        features = geojson.get("features", [])
        try:
            count = 0
            batch: list[TransmissionLine] = []

            for feat in features:
                props = feat.get("properties", {})
                record = TransmissionLine(
                    iso_id=self._iso.id,
                    voltage_kv=props.get("VOLTAGE"),
                    owner=props.get("OWNER"),
                    sub_1=props.get("SUB_1"),
                    sub_2=props.get("SUB_2"),
                    shape_length=props.get("SHAPE__Len"),
                    geometry_json=feat.get("geometry"),
                )
                batch.append(record)
                count += 1

                if len(batch) >= batch_size:
                    self.db.bulk_save_objects(batch)
                    self.db.commit()
                    batch = []

            if batch:
                self.db.bulk_save_objects(batch)
                self.db.commit()

            logger.info(f"DB: Wrote {count} transmission lines")
        except Exception as e:
            logger.warning(f"DB write failed (transmission_lines): {e}")
            self.db.rollback()

    # ------------------------------------------------------------------
    # Substations (GRIP CSV)
    # ------------------------------------------------------------------

    def write_substations(self, csv_path: Path):
        """
        Write substation records from a GRIP CSV file.

        Expected columns: substationname, bankname, division,
            facilityratingmw, facilityloadingmw2025,
            peakfacilityloadingpercent, facilitytype
        """
        if not self._iso:
            self._ensure_iso_and_zones()
        try:
            count = 0
            with open(csv_path, newline="") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    name = row.get("substationname", "").strip()
                    if not name:
                        continue

                    bank = row.get("bankname", "").strip() or None

                    existing = self.db.query(Substation).filter(
                        Substation.iso_id == self._iso.id,
                        Substation.substation_name == name,
                        Substation.bank_name == bank,
                    ).first()
                    if existing:
                        continue

                    record = Substation(
                        iso_id=self._iso.id,
                        substation_name=name,
                        bank_name=bank,
                        division=row.get("division", "").strip() or None,
                        facility_rating_mw=_safe_float(row.get("facilityratingmw")),
                        facility_loading_mw=_safe_float(row.get("facilityloadingmw2025")),
                        peak_loading_pct=_safe_float(row.get("peakfacilityloadingpercent")),
                        facility_type=row.get("facilitytype", "").strip() or None,
                    )
                    self.db.add(record)
                    count += 1

            self.db.commit()
            logger.info(f"DB: Wrote {count} substations")
        except Exception as e:
            logger.warning(f"DB write failed (substations): {e}")
            self.db.rollback()

    # ------------------------------------------------------------------
    # DER recommendations (existing)
    # ------------------------------------------------------------------

    def write_recommendations(self, recommendations: list[dict]):
        """Write DER recommendations."""
        if not self._run or not recommendations:
            return
        try:
            count = 0
            for rec in recommendations:
                zone = self._zone_lookup.get(rec.get("zone"))
                if not zone:
                    zone = self._get_or_create_zone(rec.get("zone"))
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

    # ------------------------------------------------------------------
    # Run lifecycle (existing)
    # ------------------------------------------------------------------

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


def _safe_float(val) -> Optional[float]:
    """Convert a string to float, returning None on failure."""
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


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
