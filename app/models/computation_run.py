"""Computation run tracking model.

Replaces pipeline_runs and hc_ingestion_runs with a unified run tracker
for all profile computation operations.
"""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import String, Integer, DateTime, JSON, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class ComputationRun(Base):
    __tablename__ = "computation_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_type: Mapped[str] = mapped_column(String(50), nullable=False)
        # lmp_congestion, pnode_congestion, substation_loading,
        # hosting_capacity, ba_import_stress, intersection, value_stack,
        # annotation, full_recompute
    iso_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("isos.id"), nullable=True)
    period_year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="running")
        # running, success, failed
    parameters_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    metrics_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
        # {rows_processed, profiles_created, errors, duration_sec}
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    iso: Mapped[Optional["ISO"]] = relationship()
    constraint_profiles: Mapped[list["ConstraintProfile"]] = relationship(
        back_populates="computation_run")


# Avoid circular imports
from .iso import ISO  # noqa: E402
from .constraint_profile import ConstraintProfile  # noqa: E402
