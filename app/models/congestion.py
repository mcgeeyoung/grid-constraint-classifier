"""Import Congestion pipeline models.

Four tables supporting the congestion analysis workflow:
- BalancingAuthority: reference table for ~61 US non-RTO BAs
- InterfaceLMP: raw hourly LMP at RTO interface/scheduling points
- BAHourlyData: hourly EIA-930 operational data per BA
- CongestionScore: computed congestion metrics per BA per period
"""

from typing import Optional
from datetime import date, datetime

from sqlalchemy import (
    String, Float, Integer, Boolean, Date, DateTime, JSON,
    ForeignKey, Index, BigInteger,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class BalancingAuthority(Base):
    """Reference table: all US non-RTO balancing authorities with interface mappings."""

    __tablename__ = "balancing_authorities"
    __table_args__ = (
        Index("ix_ba_code", "ba_code", unique=True),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    ba_code: Mapped[str] = mapped_column(String(10), unique=True, nullable=False)
    ba_name: Mapped[Optional[str]] = mapped_column(String(200))
    region: Mapped[Optional[str]] = mapped_column(String(50))
    interconnection: Mapped[Optional[str]] = mapped_column(String(20))
    is_rto: Mapped[bool] = mapped_column(Boolean, default=False)
    rto_neighbor: Mapped[Optional[str]] = mapped_column(String(10))
    rto_neighbor_secondary: Mapped[Optional[str]] = mapped_column(String(10))
    interface_points: Mapped[Optional[dict]] = mapped_column(JSON)
    latitude: Mapped[Optional[float]] = mapped_column(Float)
    longitude: Mapped[Optional[float]] = mapped_column(Float)
    transfer_limit_mw: Mapped[Optional[float]] = mapped_column(Float)
    transfer_limit_method: Mapped[Optional[str]] = mapped_column(String(20))
    ba_extra: Mapped[Optional[dict]] = mapped_column(JSON)

    # Relationships
    hourly_data: Mapped[list["BAHourlyData"]] = relationship(back_populates="ba")
    congestion_scores: Mapped[list["CongestionScore"]] = relationship(back_populates="ba")


class InterfaceLMP(Base):
    """Raw hourly LMP data at RTO interface/scheduling points.

    Stored separately from BA hourly data because multiple BAs may reference
    the same interface node (e.g., many SE BAs all use PJM SOUTH).
    """

    __tablename__ = "interface_lmps"
    __table_args__ = (
        Index("ix_interface_lmp_rto_node_ts", "rto", "node_id", "timestamp_utc", unique=True),
        Index("ix_interface_lmp_ts", "timestamp_utc"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    rto: Mapped[str] = mapped_column(String(10), nullable=False)
    node_id: Mapped[str] = mapped_column(String(50), nullable=False)
    timestamp_utc: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    lmp: Mapped[Optional[float]] = mapped_column(Float)
    energy_component: Mapped[Optional[float]] = mapped_column(Float)
    congestion_component: Mapped[Optional[float]] = mapped_column(Float)
    loss_component: Mapped[Optional[float]] = mapped_column(Float)
    market_type: Mapped[str] = mapped_column(String(5), default="DA")


class BAHourlyData(Base):
    """Hourly operational data per BA from EIA-930.

    LMP data is NOT stored here. Join to InterfaceLMP via the BA's
    interface_points mapping + timestamp for economic analysis.
    """

    __tablename__ = "ba_hourly_data"
    __table_args__ = (
        Index("ix_ba_hourly_ba_ts", "ba_id", "timestamp_utc", unique=True),
        Index("ix_ba_hourly_ts", "timestamp_utc"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    ba_id: Mapped[int] = mapped_column(ForeignKey("balancing_authorities.id"), nullable=False)
    timestamp_utc: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    demand_mw: Mapped[Optional[float]] = mapped_column(Float)
    net_generation_mw: Mapped[Optional[float]] = mapped_column(Float)
    total_interchange_mw: Mapped[Optional[float]] = mapped_column(Float)
    net_imports_mw: Mapped[Optional[float]] = mapped_column(Float)

    ba: Mapped["BalancingAuthority"] = relationship(back_populates="hourly_data")


class CongestionScore(Base):
    """Computed congestion metrics per BA per period (monthly or annual)."""

    __tablename__ = "congestion_scores"
    __table_args__ = (
        Index("ix_congestion_score_ba_period", "ba_id", "period_start", "period_type", unique=True),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    ba_id: Mapped[int] = mapped_column(ForeignKey("balancing_authorities.id"), nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    period_type: Mapped[Optional[str]] = mapped_column(String(10))

    # Duration metrics
    hours_total: Mapped[Optional[int]] = mapped_column(Integer)
    hours_importing: Mapped[Optional[int]] = mapped_column(Integer)
    pct_hours_importing: Mapped[Optional[float]] = mapped_column(Float)
    hours_above_80: Mapped[Optional[int]] = mapped_column(Integer)
    hours_above_90: Mapped[Optional[int]] = mapped_column(Integer)
    hours_above_95: Mapped[Optional[int]] = mapped_column(Integer)

    # Import intensity
    avg_import_pct_of_load: Mapped[Optional[float]] = mapped_column(Float)
    max_import_pct_of_load: Mapped[Optional[float]] = mapped_column(Float)

    # Economic metrics (require LMP data)
    avg_congestion_premium: Mapped[Optional[float]] = mapped_column(Float)
    congestion_opportunity_score: Mapped[Optional[float]] = mapped_column(Float)

    # Metadata
    transfer_limit_used: Mapped[Optional[float]] = mapped_column(Float)
    lmp_coverage: Mapped[Optional[str]] = mapped_column(String(10))
    hours_with_lmp_data: Mapped[Optional[int]] = mapped_column(Integer)
    data_quality_flag: Mapped[Optional[str]] = mapped_column(String(20))

    ba: Mapped["BalancingAuthority"] = relationship(back_populates="congestion_scores")
