"""DER recommendation model."""

from typing import Optional

from sqlalchemy import String, Float, Text, ForeignKey, UniqueConstraint, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class DERRecommendation(Base):
    __tablename__ = "der_recommendations"
    __table_args__ = (
        UniqueConstraint("pipeline_run_id", "zone_id", name="uq_der_recs"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    pipeline_run_id: Mapped[int] = mapped_column(ForeignKey("pipeline_runs.id"))
    zone_id: Mapped[int] = mapped_column(ForeignKey("zones.id"))
    classification: Mapped[Optional[str]] = mapped_column(String(20))
    rationale: Mapped[Optional[str]] = mapped_column(Text)
    congestion_value: Mapped[Optional[float]] = mapped_column(Float)
    primary_rec: Mapped[Optional[dict]] = mapped_column(JSON)
    secondary_rec: Mapped[Optional[dict]] = mapped_column(JSON)
    tertiary_rec: Mapped[Optional[dict]] = mapped_column(JSON)

    # Relationships
    pipeline_run: Mapped["PipelineRun"] = relationship(back_populates="der_recommendations")
    zone: Mapped["Zone"] = relationship(back_populates="der_recommendations")

    def __repr__(self) -> str:
        return f"<DERRecommendation(zone_id={self.zone_id}, cls={self.classification!r})>"


from .pipeline_run import PipelineRun  # noqa: E402
from .zone import Zone  # noqa: E402
