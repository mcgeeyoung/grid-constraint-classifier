"""Constraint-DER intersection model.

Pre-computed value from crossing a constraint profile with a DER output profile.
The coincidence factor and $/kW-yr value are the core product outputs.
"""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import String, Integer, Float, DateTime, JSON, ForeignKey, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class ConstraintDERIntersection(Base):
    __tablename__ = "constraint_der_intersections"
    __table_args__ = (
        UniqueConstraint("constraint_profile_id", "der_profile_id",
                         name="uq_cdi"),
        Index("ix_cdi_constraint", "constraint_profile_id"),
        Index("ix_cdi_der", "der_profile_id"),
        Index("ix_cdi_value", "value_per_kw_year"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    constraint_profile_id: Mapped[int] = mapped_column(
        ForeignKey("constraint_profiles.id"), nullable=False)
    der_profile_id: Mapped[int] = mapped_column(
        ForeignKey("der_profiles.id"), nullable=False)

    # Intersection results
    coincidence_factor: Mapped[float] = mapped_column(Float, nullable=False)
        # 0-1 cosine similarity
    overlap_hours: Mapped[int] = mapped_column(Integer, nullable=False)
        # Hours where both profiles > threshold
    overlap_12x24: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
        # Element-wise product of the two 12x24s

    # Dollar value
    value_per_kw_year: Mapped[float] = mapped_column(Float, nullable=False)
    value_tier: Mapped[str] = mapped_column(String(20), nullable=False)
        # premium (>=150), high (>=80), moderate (>=30), low (<30)
    value_breakdown: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # Relationships
    constraint_profile: Mapped["ConstraintProfile"] = relationship(
        back_populates="intersections")
    der_profile: Mapped["DERProfile"] = relationship(
        back_populates="intersections")


# Avoid circular imports
from .constraint_profile import ConstraintProfile  # noqa: E402
from .der_profile import DERProfile  # noqa: E402
