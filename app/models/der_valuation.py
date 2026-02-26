"""DER valuation model (computed constraint-relief values)."""

from typing import Optional

from sqlalchemy import String, Float, ForeignKey, UniqueConstraint, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class DERValuation(Base):
    __tablename__ = "der_valuations"
    __table_args__ = (
        UniqueConstraint("pipeline_run_id", "der_location_id", name="uq_der_valuations"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    pipeline_run_id: Mapped[int] = mapped_column(ForeignKey("pipeline_runs.id"))
    der_location_id: Mapped[int] = mapped_column(ForeignKey("der_locations.id"))
    zone_congestion_value: Mapped[Optional[float]] = mapped_column(Float)
    pnode_multiplier: Mapped[Optional[float]] = mapped_column(Float)
    substation_loading_value: Mapped[Optional[float]] = mapped_column(Float)
    feeder_capacity_value: Mapped[Optional[float]] = mapped_column(Float)
    total_constraint_relief_value: Mapped[Optional[float]] = mapped_column(Float)
    coincidence_factor: Mapped[Optional[float]] = mapped_column(Float)
    effective_capacity_mw: Mapped[Optional[float]] = mapped_column(Float)
    value_tier: Mapped[Optional[str]] = mapped_column(String(20))
    value_breakdown: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Relationships
    pipeline_run: Mapped["PipelineRun"] = relationship()
    der_location: Mapped["DERLocation"] = relationship(back_populates="valuations")

    def __repr__(self) -> str:
        return (
            f"<DERValuation(der_location_id={self.der_location_id}, "
            f"value=${self.total_constraint_relief_value}, tier={self.value_tier!r})>"
        )


from .pipeline_run import PipelineRun  # noqa: E402
from .der_location import DERLocation  # noqa: E402
