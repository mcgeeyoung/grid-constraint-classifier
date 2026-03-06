"""Constraint annotation model.

Regulatory context linked directly to constraint profiles: IRP citations,
grid plans, deferral opportunities, rate cases, and resource needs.
"""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import String, Float, DateTime, Text, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class ConstraintAnnotation(Base):
    __tablename__ = "constraint_annotations"
    __table_args__ = (
        Index("ix_ca_profile", "constraint_profile_id"),
        Index("ix_ca_type", "annotation_type"),
        Index("ix_ca_utility", "utility_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    constraint_profile_id: Mapped[int] = mapped_column(
        ForeignKey("constraint_profiles.id"), nullable=False)
    annotation_type: Mapped[str] = mapped_column(String(30), nullable=False)
        # irp_citation, grid_plan, deferral_opportunity, rate_case, resource_need
    utility_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("utilities.id"), nullable=True)
    filing_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("filings.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    planned_solution: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    deferral_value_estimate: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True)  # $/year
    source_url: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    source_document: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # Relationships
    constraint_profile: Mapped["ConstraintProfile"] = relationship(
        back_populates="annotations")
    utility: Mapped[Optional["Utility"]] = relationship()
    filing: Mapped[Optional["Filing"]] = relationship()


# Avoid circular imports
from .constraint_profile import ConstraintProfile  # noqa: E402
from .utility import Utility  # noqa: E402
from .filing import Filing  # noqa: E402
