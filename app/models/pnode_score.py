"""Pnode severity score model."""

from typing import Optional

from sqlalchemy import Index, String, Float, ForeignKey, UniqueConstraint, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class PnodeScore(Base):
    __tablename__ = "pnode_scores"
    __table_args__ = (
        UniqueConstraint("pipeline_run_id", "pnode_id", name="uq_pnode_scores"),
        Index("ix_pnode_scores_pipeline_run_id", "pipeline_run_id"),
        Index("ix_pnode_scores_pnode_id", "pnode_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    pipeline_run_id: Mapped[int] = mapped_column(ForeignKey("pipeline_runs.id"))
    pnode_id: Mapped[int] = mapped_column(ForeignKey("pnodes.id"))
    severity_score: Mapped[float] = mapped_column(Float, nullable=False)
    tier: Mapped[str] = mapped_column(String(20), nullable=False)
    avg_congestion: Mapped[Optional[float]] = mapped_column(Float)
    max_congestion: Mapped[Optional[float]] = mapped_column(Float)
    congested_hours_pct: Mapped[Optional[float]] = mapped_column(Float)
    constraint_loadshape: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Relationships
    pipeline_run: Mapped["PipelineRun"] = relationship(back_populates="pnode_scores")
    pnode: Mapped["Pnode"] = relationship(back_populates="scores")

    def __repr__(self) -> str:
        return f"<PnodeScore(pnode_id={self.pnode_id}, score={self.severity_score:.3f})>"


from .pipeline_run import PipelineRun  # noqa: E402
from .pnode import Pnode  # noqa: E402
