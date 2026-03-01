"""Hosting capacity models: ingestion tracking, per-feeder records, and summaries.

HostingCapacityRecord stores per-feeder hosting capacity data from 97+ utilities.
Each record links to a utility and ingestion run, with optional FK links to the
existing physical hierarchy (Substation/Feeder) populated by spatial matching.

All capacity fields are normalized to MW during ingestion.
"""

from datetime import date, datetime, timezone
from typing import Optional

from geoalchemy2 import Geometry
from sqlalchemy import (
    Boolean, Date, DateTime, Float, ForeignKey, Index, Integer,
    JSON, String, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class HCIngestionRun(Base):
    """Tracks each hosting capacity data pull from a utility source."""

    __tablename__ = "hc_ingestion_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    utility_id: Mapped[int] = mapped_column(ForeignKey("utilities.id"), nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), default="running")
    records_fetched: Mapped[Optional[int]] = mapped_column(Integer)
    records_written: Mapped[Optional[int]] = mapped_column(Integer)
    error_message: Mapped[Optional[str]] = mapped_column(String(1000))
    source_url: Mapped[Optional[str]] = mapped_column(String(500))

    # Relationships
    utility: Mapped["Utility"] = relationship(back_populates="ingestion_runs")

    def __repr__(self) -> str:
        return f"<HCIngestionRun(id={self.id}, status={self.status!r})>"


class HostingCapacityRecord(Base):
    """Per-feeder hosting capacity data from a single utility ingestion."""

    __tablename__ = "hosting_capacity_records"
    __table_args__ = (
        UniqueConstraint(
            "utility_id", "feeder_id_external", "ingestion_run_id",
            name="uq_hc_record",
        ),
        Index("ix_hc_utility", "utility_id"),
        Index("ix_hc_ingestion_run", "ingestion_run_id"),
        Index("ix_hc_geom", "geom", postgresql_using="gist"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    utility_id: Mapped[int] = mapped_column(ForeignKey("utilities.id"), nullable=False)
    ingestion_run_id: Mapped[int] = mapped_column(
        ForeignKey("hc_ingestion_runs.id"), nullable=False,
    )

    # Feeder identification (from utility's data)
    feeder_id_external: Mapped[str] = mapped_column(String(200), nullable=False)
    feeder_name: Mapped[Optional[str]] = mapped_column(String(300))
    substation_name: Mapped[Optional[str]] = mapped_column(String(300))

    # Optional links to existing physical hierarchy (populated by spatial matching)
    substation_id: Mapped[Optional[int]] = mapped_column(ForeignKey("substations.id"))
    feeder_id: Mapped[Optional[int]] = mapped_column(ForeignKey("feeders.id"))

    # Canonical capacity fields (all normalized to MW)
    hosting_capacity_mw: Mapped[Optional[float]] = mapped_column(Float)
    hosting_capacity_min_mw: Mapped[Optional[float]] = mapped_column(Float)
    hosting_capacity_max_mw: Mapped[Optional[float]] = mapped_column(Float)
    installed_dg_mw: Mapped[Optional[float]] = mapped_column(Float)
    queued_dg_mw: Mapped[Optional[float]] = mapped_column(Float)
    remaining_capacity_mw: Mapped[Optional[float]] = mapped_column(Float)

    # Constraint info
    constraining_metric: Mapped[Optional[str]] = mapped_column(String(100))

    # Feeder characteristics
    voltage_kv: Mapped[Optional[float]] = mapped_column(Float)
    phase_config: Mapped[Optional[str]] = mapped_column(String(20))
    is_overhead: Mapped[Optional[bool]] = mapped_column(Boolean)
    is_network: Mapped[Optional[bool]] = mapped_column(Boolean)

    # Geometry
    centroid_lat: Mapped[Optional[float]] = mapped_column(Float)
    centroid_lon: Mapped[Optional[float]] = mapped_column(Float)
    geom = mapped_column(Geometry("POINT", srid=4326), nullable=True, deferred=True)
    geometry_json: Mapped[Optional[dict]] = mapped_column(JSON)

    # Provenance
    record_date: Mapped[Optional[date]] = mapped_column(Date)
    raw_attributes: Mapped[Optional[dict]] = mapped_column(JSON)

    # Relationships
    utility: Mapped["Utility"] = relationship(back_populates="hosting_capacity_records")
    ingestion_run: Mapped["HCIngestionRun"] = relationship()

    def __repr__(self) -> str:
        return (
            f"<HostingCapacityRecord(utility={self.utility_id}, "
            f"feeder={self.feeder_id_external!r})>"
        )


class HostingCapacitySummary(Base):
    """Pre-aggregated per-utility hosting capacity statistics."""

    __tablename__ = "hosting_capacity_summaries"

    id: Mapped[int] = mapped_column(primary_key=True)
    utility_id: Mapped[int] = mapped_column(
        ForeignKey("utilities.id"), unique=True, nullable=False,
    )
    total_feeders: Mapped[int] = mapped_column(Integer, default=0)
    total_hosting_capacity_mw: Mapped[float] = mapped_column(Float, default=0.0)
    total_installed_dg_mw: Mapped[float] = mapped_column(Float, default=0.0)
    total_remaining_capacity_mw: Mapped[float] = mapped_column(Float, default=0.0)
    avg_utilization_pct: Mapped[Optional[float]] = mapped_column(Float)
    constrained_feeders_count: Mapped[int] = mapped_column(Integer, default=0)
    constraint_breakdown: Mapped[Optional[dict]] = mapped_column(JSON)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    utility: Mapped["Utility"] = relationship()

    def __repr__(self) -> str:
        return f"<HostingCapacitySummary(utility_id={self.utility_id})>"


from .utility import Utility  # noqa: E402
