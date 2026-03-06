"""Location value stack model.

Composite value across all constraint layers at a location for a specific DER type.
Stacks congestion, loading, capacity, and import stress values into a total $/kW-yr.
"""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import String, Integer, Float, DateTime, JSON, ForeignKey, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class LocationValueStack(Base):
    __tablename__ = "location_value_stacks"
    __table_args__ = (
        UniqueConstraint("location_level", "location_id", "der_profile_id",
                         "period_year", name="uq_lvs"),
        Index("ix_lvs_location", "location_level", "location_id"),
        Index("ix_lvs_value", "total_value_per_kw_year"),
        Index("ix_lvs_tier", "value_tier"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    location_level: Mapped[str] = mapped_column(String(20), nullable=False)
    location_id: Mapped[int] = mapped_column(Integer, nullable=False)
    der_profile_id: Mapped[int] = mapped_column(
        ForeignKey("der_profiles.id"), nullable=False)

    # Per-layer values
    congestion_value_per_kw_year: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True, default=0.0)
    loading_value_per_kw_year: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True, default=0.0)
    capacity_value_per_kw_year: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True, default=0.0)
    import_stress_value_per_kw_year: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True, default=0.0)

    # Composite
    total_value_per_kw_year: Mapped[float] = mapped_column(Float, nullable=False)
    composite_coincidence_factor: Mapped[float] = mapped_column(Float, nullable=False)
    value_tier: Mapped[str] = mapped_column(String(20), nullable=False)

    # Which constraint layers contributed
    constraint_layers: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
        # [{type, profile_id, contribution_pct}, ...]

    period_year: Mapped[int] = mapped_column(Integer, nullable=False)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # Relationships
    der_profile: Mapped["DERProfile"] = relationship()


# Avoid circular imports
from .der_profile import DERProfile  # noqa: E402
