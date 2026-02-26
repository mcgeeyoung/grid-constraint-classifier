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
    TransmissionLine, Substation, Feeder,
    HierarchyScore, DERValuation, DERLocation,
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
            peakfacilityloadingpercent, facilitytype, lat, lon
        """
        if not self._iso:
            self._ensure_iso_and_zones()
        try:
            created = 0
            updated = 0
            with open(csv_path, newline="") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    name = row.get("substationname", "").strip()
                    if not name:
                        continue

                    bank = row.get("bankname", "").strip() or None
                    lat = _safe_float(row.get("lat"))
                    lon = _safe_float(row.get("lon"))

                    existing = self.db.query(Substation).filter(
                        Substation.iso_id == self._iso.id,
                        Substation.substation_name == name,
                        Substation.bank_name == bank,
                    ).first()
                    if existing:
                        # Update existing records missing lat/lon or loading data
                        changed = False
                        if lat is not None and existing.lat is None:
                            existing.lat = lat
                            existing.lon = lon
                            changed = True
                        if existing.peak_loading_pct is None:
                            pct = _safe_float(row.get("peakfacilityloadingpercent"))
                            if pct is not None:
                                existing.peak_loading_pct = pct
                                existing.facility_rating_mw = _safe_float(row.get("facilityratingmw"))
                                existing.facility_loading_mw = _safe_float(row.get("facilityloadingmw2025"))
                                changed = True
                        if changed:
                            updated += 1
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
                        lat=lat,
                        lon=lon,
                    )
                    self.db.add(record)
                    created += 1

            self.db.commit()
            logger.info(f"DB: Wrote {created} substations, updated {updated} existing")
        except Exception as e:
            logger.warning(f"DB write failed (substations): {e}")
            self.db.rollback()

    # ------------------------------------------------------------------
    # Feeders (distribution feeders off substations)
    # ------------------------------------------------------------------

    def write_feeders(self, feeders: list[dict], batch_size: int = 500):
        """
        Write feeder records from a list of dicts.

        Args:
            feeders: list of dicts with keys:
                substation_id, feeder_id_external, capacity_mw,
                peak_loading_mw, peak_loading_pct, voltage_kv,
                geometry_json (optional)
        Deduplicates on (substation_id, feeder_id_external).
        """
        if not feeders:
            return
        try:
            created = 0
            batch: list[Feeder] = []

            for f in feeders:
                sub_id = f.get("substation_id")
                ext_id = f.get("feeder_id_external")
                if not sub_id:
                    continue

                # Check for existing record
                if ext_id:
                    existing = self.db.query(Feeder).filter(
                        Feeder.substation_id == sub_id,
                        Feeder.feeder_id_external == ext_id,
                    ).first()
                    if existing:
                        continue

                record = Feeder(
                    substation_id=sub_id,
                    feeder_id_external=ext_id,
                    capacity_mw=f.get("capacity_mw"),
                    peak_loading_mw=f.get("peak_loading_mw"),
                    peak_loading_pct=f.get("peak_loading_pct"),
                    voltage_kv=f.get("voltage_kv"),
                    geometry_json=f.get("geometry_json"),
                )
                batch.append(record)
                created += 1

                if len(batch) >= batch_size:
                    self.db.bulk_save_objects(batch)
                    self.db.commit()
                    batch = []

            if batch:
                self.db.bulk_save_objects(batch)
                self.db.commit()

            logger.info(f"DB: Wrote {created} feeders")
        except Exception as e:
            logger.warning(f"DB write failed (feeders): {e}")
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
    # Hierarchy scores (new)
    # ------------------------------------------------------------------

    def write_hierarchy_scores(self, scores: list[dict], batch_size: int = 500):
        """
        Write pre-computed constraint scores at each hierarchy level.

        Args:
            scores: list of dicts with keys:
                level (iso/zone/substation/feeder/circuit), entity_id,
                congestion_score, loading_score, combined_score,
                constraint_tier, constraint_loadshape
        """
        if not self._run or not scores:
            return
        try:
            count = 0
            batch: list[HierarchyScore] = []

            for s in scores:
                record = HierarchyScore(
                    pipeline_run_id=self._run.id,
                    level=s["level"],
                    entity_id=s["entity_id"],
                    congestion_score=s.get("congestion_score"),
                    loading_score=s.get("loading_score"),
                    combined_score=s.get("combined_score"),
                    constraint_tier=s.get("constraint_tier"),
                    constraint_loadshape=s.get("constraint_loadshape"),
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

            logger.info(f"DB: Wrote {count} hierarchy scores")
        except Exception as e:
            logger.warning(f"DB write failed (hierarchy_scores): {e}")
            self.db.rollback()

    # ------------------------------------------------------------------
    # DER valuations (new)
    # ------------------------------------------------------------------

    def write_der_valuations(self, valuations: list[dict], batch_size: int = 500):
        """
        Write computed DER constraint-relief valuations.

        Args:
            valuations: list of dicts with keys:
                der_location_id, zone_congestion_value, pnode_multiplier,
                substation_loading_value, feeder_capacity_value,
                total_constraint_relief_value, coincidence_factor,
                effective_capacity_mw, value_tier, value_breakdown
        """
        if not self._run or not valuations:
            return
        try:
            count = 0
            batch: list[DERValuation] = []

            for v in valuations:
                record = DERValuation(
                    pipeline_run_id=self._run.id,
                    der_location_id=v["der_location_id"],
                    zone_congestion_value=v.get("zone_congestion_value"),
                    pnode_multiplier=v.get("pnode_multiplier"),
                    substation_loading_value=v.get("substation_loading_value"),
                    feeder_capacity_value=v.get("feeder_capacity_value"),
                    total_constraint_relief_value=v.get("total_constraint_relief_value"),
                    coincidence_factor=v.get("coincidence_factor"),
                    effective_capacity_mw=v.get("effective_capacity_mw"),
                    value_tier=v.get("value_tier"),
                    value_breakdown=v.get("value_breakdown"),
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

            logger.info(f"DB: Wrote {count} DER valuations")
        except Exception as e:
            logger.warning(f"DB write failed (der_valuations): {e}")
            self.db.rollback()

    # ------------------------------------------------------------------
    # Backfill: link substations to zones via spatial proximity
    # ------------------------------------------------------------------

    def backfill_substation_zones(self):
        """
        One-time spatial join: assign zone_id and nearest_pnode_id to
        substations that have lat/lon but no zone linkage.

        Uses haversine distance to find the containing or nearest zone
        (via centroid) and the nearest pnode.
        """
        if not self._iso:
            self._ensure_iso_and_zones()

        from math import radians, sin, cos, sqrt, atan2

        def _haversine(lat1, lon1, lat2, lon2):
            R = 6371.0
            dlat = radians(lat2 - lat1)
            dlon = radians(lon2 - lon1)
            a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
            return R * 2 * atan2(sqrt(a), sqrt(1 - a))

        try:
            # Load zones with centroids
            zones = self.db.query(Zone).filter(
                Zone.iso_id == self._iso.id,
                Zone.centroid_lat.isnot(None),
            ).all()

            # Load pnodes with coordinates
            pnodes = self.db.query(Pnode).filter(
                Pnode.iso_id == self._iso.id,
                Pnode.lat.isnot(None),
            ).all()

            # Load substations needing linkage
            subs = self.db.query(Substation).filter(
                Substation.iso_id == self._iso.id,
                Substation.lat.isnot(None),
                Substation.zone_id.is_(None),
            ).all()

            if not subs:
                logger.info("DB: No substations need zone backfill")
                return

            # Try shapely for polygon containment
            use_polygons = False
            zone_polygons = {}
            try:
                from shapely.geometry import shape, Point
                use_polygons = True
                for z in zones:
                    if z.boundary_geojson:
                        try:
                            zone_polygons[z.id] = (z, shape(z.boundary_geojson))
                        except Exception:
                            pass
            except ImportError:
                pass

            zone_linked = 0
            pnode_linked = 0

            for sub in subs:
                # Zone assignment: polygon first, then centroid fallback
                matched_zone = None

                if use_polygons and zone_polygons:
                    pt = Point(sub.lon, sub.lat)
                    for zid, (z, poly) in zone_polygons.items():
                        if poly.contains(pt):
                            matched_zone = z
                            break

                if not matched_zone and zones:
                    best_dist = float("inf")
                    for z in zones:
                        d = _haversine(sub.lat, sub.lon, z.centroid_lat, z.centroid_lon)
                        if d < best_dist:
                            best_dist = d
                            matched_zone = z

                if matched_zone:
                    sub.zone_id = matched_zone.id
                    zone_linked += 1

                # Nearest pnode
                if pnodes:
                    best_pnode = None
                    best_dist = float("inf")
                    for p in pnodes:
                        d = _haversine(sub.lat, sub.lon, p.lat, p.lon)
                        if d < best_dist:
                            best_dist = d
                            best_pnode = p
                    if best_pnode and best_dist < 50.0:
                        sub.nearest_pnode_id = best_pnode.id
                        pnode_linked += 1

            self.db.commit()
            logger.info(
                f"DB: Backfill substations — {zone_linked} zones linked, "
                f"{pnode_linked} pnodes linked (of {len(subs)} total)"
            )
        except Exception as e:
            logger.warning(f"DB backfill failed (substation_zones): {e}")
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
