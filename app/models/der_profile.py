"""DER output profile model.

Stores 12x24 output patterns for each DER type. Canonical profiles are seeded
from core/der_profiles.py. Location-specific profiles can be added from NREL SAM
or metered WattCarbon data.
"""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import String, Integer, Float, Boolean, DateTime, JSON, Text, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class DERProfile(Base):
    __tablename__ = "der_profiles"
    __table_args__ = (
        UniqueConstraint("der_type", "profile_source", "location_id",
                         name="uq_der_profile"),
        Index("ix_dp_type", "der_type"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    der_type: Mapped[str] = mapped_column(String(50), nullable=False)
        # solar, wind, storage, demand_response, energy_efficiency,
        # weatherization, combined_heat_power, fuel_cell
    eac_category: Mapped[str] = mapped_column(String(20), nullable=False)
        # variable, consistent, dispatchable
    profile_source: Mapped[str] = mapped_column(String(50), nullable=False)
        # canonical, nrel_sam, wattcarbon_metered, custom
    location_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
        # NULL for canonical profiles; set for location-specific

    # The 12x24 profile (normalized 0-1), NULL for dispatchable types
    profile_12x24: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Dispatchable DER parameters
    is_dispatchable: Mapped[bool] = mapped_column(Boolean, default=False)
    max_dispatch_hours: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    dispatch_power_mw: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    ramp_rate_mw_per_min: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Performance
    capacity_factor: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # Relationships
    intersections: Mapped[list["ConstraintDERIntersection"]] = relationship(
        back_populates="der_profile")


# Avoid circular imports
from .constraint_der_intersection import ConstraintDERIntersection  # noqa: E402
