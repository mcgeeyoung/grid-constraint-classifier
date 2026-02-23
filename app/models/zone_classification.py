"""Zone classification results model."""

from typing import Optional

from sqlalchemy import String, Float, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class ZoneClassification(Base):
    __tablename__ = "zone_classifications"
    __table_args__ = (
        UniqueConstraint("pipeline_run_id", "zone_id", name="uq_zone_cls"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    pipeline_run_id: Mapped[int] = mapped_column(ForeignKey("pipeline_runs.id"))
    zone_id: Mapped[int] = mapped_column(ForeignKey("zones.id"))
    classification: Mapped[str] = mapped_column(String(20), nullable=False)
    transmission_score: Mapped[float] = mapped_column(Float, nullable=False)
    generation_score: Mapped[float] = mapped_column(Float, nullable=False)
    avg_abs_congestion: Mapped[Optional[float]] = mapped_column(Float)
    max_congestion: Mapped[Optional[float]] = mapped_column(Float)
    congested_hours_pct: Mapped[Optional[float]] = mapped_column(Float)

    # Relationships
    pipeline_run: Mapped["PipelineRun"] = relationship(back_populates="classifications")
    zone: Mapped["Zone"] = relationship(back_populates="classifications")

    def __repr__(self) -> str:
        return f"<ZoneClassification(zone_id={self.zone_id}, cls={self.classification!r})>"


from .pipeline_run import PipelineRun  # noqa: E402
from .zone import Zone  # noqa: E402
