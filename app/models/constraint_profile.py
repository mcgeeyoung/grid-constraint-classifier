"""Constraint profile model.

The central abstraction: every grid constraint normalized into a 12x24 profile
(month x hour matrix) representing constraint intensity. Unifies zone congestion,
pnode congestion, substation loading, feeder capacity, and BA import stress.
"""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    String, Integer, Float, SmallInteger, DateTime, JSON, ForeignKey,
    Index, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class ConstraintProfile(Base):
    __tablename__ = "constraint_profiles"
    __table_args__ = (
        UniqueConstraint(
            "location_level", "location_id", "constraint_type",
            "source_type", "period_year",
            name="uq_constraint_profile"),
        Index("ix_cp_location", "location_level", "location_id"),
        Index("ix_cp_type_year", "constraint_type", "period_year"),
        Index("ix_cp_severity", "severity_score"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    location_level: Mapped[str] = mapped_column(String(20), nullable=False)
        # zone, pnode, substation, feeder, circuit, ba
    location_id: Mapped[int] = mapped_column(Integer, nullable=False)
    constraint_type: Mapped[str] = mapped_column(String(20), nullable=False)
        # congestion, loading, capacity, import_stress
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
        # lmp_zone, lmp_pnode, grip, hosting_capacity, eia930
    period_year: Mapped[int] = mapped_column(Integer, nullable=False)

    # The 12x24 profile (288 values)
    # {"1": [24 floats], "2": [24 floats], ..., "12": [24 floats]}
    profile_12x24: Mapped[dict] = mapped_column(JSON, nullable=False)

    # Summary statistics
    peak_intensity: Mapped[float] = mapped_column(Float, nullable=False)
    peak_month: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    peak_hour: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    mean_intensity: Mapped[float] = mapped_column(Float, nullable=False)
    total_constrained_hours: Mapped[int] = mapped_column(Integer, nullable=False)
    constrained_hours_pct: Mapped[float] = mapped_column(Float, nullable=False)

    # Severity scoring (0-1, normalized within location_level + constraint_type)
    severity_score: Mapped[float] = mapped_column(Float, nullable=False)
    severity_tier: Mapped[str] = mapped_column(String(20), nullable=False)
        # critical (>=0.75), elevated (>=0.50), moderate (>=0.25), low

    # Economic valuation
    avg_marginal_cost: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
        # $/MWh for congestion, $/kW-yr for loading/capacity
    annual_cost: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Provenance
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    computation_run_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("computation_runs.id"), nullable=True)

    # Relationships
    computation_run: Mapped[Optional["ComputationRun"]] = relationship(
        back_populates="constraint_profiles")
    annotations: Mapped[list["ConstraintAnnotation"]] = relationship(
        back_populates="constraint_profile")
    intersections: Mapped[list["ConstraintDERIntersection"]] = relationship(
        back_populates="constraint_profile")


# Avoid circular imports
from .computation_run import ComputationRun  # noqa: E402
from .constraint_annotation import ConstraintAnnotation  # noqa: E402
from .constraint_der_intersection import ConstraintDERIntersection  # noqa: E402
