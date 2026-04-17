"""Postgres models for Dominion DER program (DA node congestion + enrollment)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class DominionDaIngestionRun(Base):
    """
    One PJM pull (or attempted pull) for a given operating day / zone / LMP type.

    ``idempotency_key`` is deterministic so a scheduled job can safely retry:
    same key + status success => skip unless a force-refresh path is used.
    ``retrieved_at_utc`` is the as-of timestamp for market data provenance.
    """

    __tablename__ = "dominion_da_ingestion_runs"
    __table_args__ = (UniqueConstraint("idempotency_key", name="uq_dominion_da_runs_idem"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    idempotency_key: Mapped[str] = mapped_column(String(220), nullable=False)
    operating_date: Mapped[date] = mapped_column(Date, nullable=False)
    zone_code: Mapped[str] = mapped_column(String(20), nullable=False, default="DOM")
    lmp_type: Mapped[str] = mapped_column(String(20), nullable=False, default="LOAD")
    data_source: Mapped[str] = mapped_column(String(80), nullable=False, default="pjm_da_hrl_lmps")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    retrieved_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    request_started_at_utc: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    request_completed_at_utc: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    row_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    query_date_range: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    hourly_rows: Mapped[list["DominionDaNodeHourly"]] = relationship(
        back_populates="ingestion_run", cascade="all, delete-orphan"
    )
    dispatch_device_hours: Mapped[list["DominionDispatchDeviceHour"]] = relationship(
        "DominionDispatchDeviceHour",
        back_populates="ingestion_run",
        cascade="all, delete-orphan",
    )


class DominionDaNodeHourly(Base):
    """Hourly DA node LMP row (congestion component) tied to an ingestion run."""

    __tablename__ = "dominion_da_node_hourly"
    __table_args__ = (
        UniqueConstraint(
            "ingestion_run_id",
            "pnode_id_external",
            "interval_start_utc",
            name="uq_dominion_da_node_hourly_run_pnode_ts",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ingestion_run_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("dominion_da_ingestion_runs.id", ondelete="CASCADE"), nullable=False
    )
    operating_date: Mapped[date] = mapped_column(Date, nullable=False)
    zone_code: Mapped[str] = mapped_column(String(20), nullable=False)
    lmp_type: Mapped[str] = mapped_column(String(20), nullable=False)
    interval_start_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    pnode_id_external: Mapped[str] = mapped_column(String(50), nullable=False)
    pnode_name: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    congestion_price_da: Mapped[Optional[float]] = mapped_column(Numeric(18, 6), nullable=True)
    total_lmp_da: Mapped[Optional[float]] = mapped_column(Numeric(18, 6), nullable=True)
    marginal_loss_price_da: Mapped[Optional[float]] = mapped_column(Numeric(18, 6), nullable=True)
    system_energy_price_da: Mapped[Optional[float]] = mapped_column(Numeric(18, 6), nullable=True)

    ingestion_run: Mapped["DominionDaIngestionRun"] = relationship(back_populates="hourly_rows")


class DominionDevice(Base):
    """
    Enrolled device mapped to a PJM pnode, with optional neighbor fallback order
    and a piecewise curve (JSON) for congestion -> dispatch signal.

    ``pjm_load_zone_code`` is always **DOM** for this program (PJM Dominion Virginia
    load zone). It remains explicit for settlement semantics and joins.

    ``primary_pnode_name`` optional label from PJM (helps geocode / map tooltips).
    ``asset_lat`` / ``asset_lon`` / ``asset_display_name`` optional physical site for maps.

    ``neighbor_pnode_ids``: JSON array of strings, highest priority first.
    ``piecewise_curve``: JSON array of knots
    ``[{"congestion": -5.0, "signal": 0.0}, {"congestion": 10.0, "signal": 1.0}]``
    (piecewise linear in ``congestion``, flat extrapolation outside range).
    """

    __tablename__ = "dominion_devices"
    __table_args__ = (UniqueConstraint("device_id_external", name="uq_dominion_devices_ext_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_id_external: Mapped[str] = mapped_column(String(120), nullable=False)
    pjm_load_zone_code: Mapped[str] = mapped_column(String(20), nullable=False, default="DOM")
    primary_pnode_id: Mapped[str] = mapped_column(String(50), nullable=False)
    primary_pnode_name: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    asset_lat: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    asset_lon: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    asset_display_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    neighbor_pnode_ids: Mapped[Optional[list[Any]]] = mapped_column(JSON, nullable=True)
    piecewise_curve: Mapped[Optional[list[Any]]] = mapped_column(JSON, nullable=True)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class DominionDispatchDeviceHour(Base):
    """
    Per-device hourly dispatch row derived from a DA ingestion run (provenance via FK).

    ``ingestion_run_id`` ties this row to the same PJM snapshot as ``dominion_da_node_hourly``.
    ``pjm_load_zone_code`` is copied from enrollment for settlement-zone traceability.

    ``period_tier`` / ``dispatch_mandatory`` / ``dispatch_signal_program`` implement
    optional (stressed) vs mandatory (extreme) dispatch intensity vs raw ``dispatch_signal``.
    """

    __tablename__ = "dominion_dispatch_device_hourly"
    __table_args__ = (
        UniqueConstraint(
            "ingestion_run_id",
            "device_id_external",
            "interval_start_utc",
            name="uq_dom_dispatch_run_dev_ts",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ingestion_run_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("dominion_da_ingestion_runs.id", ondelete="CASCADE"), nullable=False
    )
    device_id_external: Mapped[str] = mapped_column(String(120), nullable=False)
    pjm_load_zone_code: Mapped[str] = mapped_column(String(20), nullable=False, default="DOM")
    primary_pnode_id: Mapped[str] = mapped_column(String(50), nullable=False)
    interval_start_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    raw_congestion: Mapped[Optional[float]] = mapped_column(Numeric(18, 6), nullable=True)
    resolved_congestion: Mapped[Optional[float]] = mapped_column(Numeric(18, 6), nullable=True)
    resolution_strategy: Mapped[str] = mapped_column(String(40), nullable=False)
    source_pnode_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    dispatch_signal: Mapped[Optional[float]] = mapped_column(Numeric(18, 6), nullable=True)
    extreme_abs_threshold_usd: Mapped[Optional[float]] = mapped_column(Numeric(18, 6), nullable=True)
    period_tier: Mapped[Optional[str]] = mapped_column(String(24), nullable=True)
    dispatch_mandatory: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    dispatch_signal_program: Mapped[Optional[float]] = mapped_column(Numeric(18, 6), nullable=True)
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    ingestion_run: Mapped["DominionDaIngestionRun"] = relationship(
        "DominionDaIngestionRun", back_populates="dispatch_device_hours"
    )
