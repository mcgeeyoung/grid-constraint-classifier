"""Monitor event model for tracking scheduled job executions and alerts.

Each row represents a single execution of a monitoring job (docket check,
HC refresh, EIA update, etc.) with its outcome and any alerts generated.
"""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, Index, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class MonitorEvent(Base):
    """A single execution of a monitoring job."""

    __tablename__ = "monitor_events"
    __table_args__ = (
        Index("ix_me_job_name", "job_name"),
        Index("ix_me_status", "status"),
        Index("ix_me_started_at", "started_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    # Job identification
    job_name: Mapped[str] = mapped_column(String(100), nullable=False)
    # job_name: docket_watchlist, hc_refresh, eia_update, ferc_714,
    #   iso_planning, coverage_snapshot, staleness_check, health_check

    # Execution
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    duration_sec: Mapped[Optional[float]] = mapped_column()
    status: Mapped[str] = mapped_column(String(20), default="running")
    # status: running, success, partial, failed, skipped

    # Results
    records_checked: Mapped[int] = mapped_column(Integer, default=0)
    records_updated: Mapped[int] = mapped_column(Integer, default=0)
    new_items_found: Mapped[int] = mapped_column(Integer, default=0)
    alerts_generated: Mapped[int] = mapped_column(Integer, default=0)

    # Details
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    summary: Mapped[Optional[str]] = mapped_column(String(1000))
    details_json: Mapped[Optional[dict]] = mapped_column(JSON)

    def __repr__(self) -> str:
        return (
            f"<MonitorEvent(job={self.job_name!r}, status={self.status!r}, "
            f"started={self.started_at})>"
        )
