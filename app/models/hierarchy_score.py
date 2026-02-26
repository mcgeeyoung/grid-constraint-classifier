"""Hierarchy score model (pre-computed constraint scores at each hierarchy level)."""

from typing import Optional

from sqlalchemy import String, Float, Integer, ForeignKey, UniqueConstraint, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class HierarchyScore(Base):
    __tablename__ = "hierarchy_scores"
    __table_args__ = (
        UniqueConstraint(
            "pipeline_run_id", "level", "entity_id",
            name="uq_hierarchy_scores",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    pipeline_run_id: Mapped[int] = mapped_column(ForeignKey("pipeline_runs.id"))
    level: Mapped[str] = mapped_column(String(20), nullable=False)
    entity_id: Mapped[int] = mapped_column(Integer, nullable=False)
    congestion_score: Mapped[Optional[float]] = mapped_column(Float)
    loading_score: Mapped[Optional[float]] = mapped_column(Float)
    combined_score: Mapped[Optional[float]] = mapped_column(Float)
    constraint_tier: Mapped[Optional[str]] = mapped_column(String(20))
    constraint_loadshape: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Relationships
    pipeline_run: Mapped["PipelineRun"] = relationship()

    def __repr__(self) -> str:
        return (
            f"<HierarchyScore(level={self.level!r}, entity_id={self.entity_id}, "
            f"combined={self.combined_score})>"
        )


from .pipeline_run import PipelineRun  # noqa: E402
