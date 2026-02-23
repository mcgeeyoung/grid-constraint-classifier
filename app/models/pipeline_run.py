"""Pipeline run tracking model."""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import String, Integer, ForeignKey, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class PipelineRun(Base):
    __tablename__ = "pipeline_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    iso_id: Mapped[int] = mapped_column(ForeignKey("isos.id"), nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    status: Mapped[str] = mapped_column(String(20), default="running")
    zone_lmp_rows: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    iso: Mapped["ISO"] = relationship(back_populates="pipeline_runs")
    classifications: Mapped[list["ZoneClassification"]] = relationship(back_populates="pipeline_run")
    pnode_scores: Mapped[list["PnodeScore"]] = relationship(back_populates="pipeline_run")
    der_recommendations: Mapped[list["DERRecommendation"]] = relationship(back_populates="pipeline_run")

    def __repr__(self) -> str:
        return f"<PipelineRun(id={self.id}, status={self.status!r})>"


from .iso import ISO  # noqa: E402
from .zone_classification import ZoneClassification  # noqa: E402
from .pnode_score import PnodeScore  # noqa: E402
from .der_recommendation import DERRecommendation  # noqa: E402
