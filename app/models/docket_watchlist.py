"""Docket watchlist model for tracking PUC proceedings of interest."""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class DocketWatch(Base):
    """A docket/proceeding being actively monitored for new filings."""

    __tablename__ = "docket_watches"
    __table_args__ = (
        Index("ix_dw_state", "state"),
        Index("ix_dw_active", "is_active"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    state: Mapped[str] = mapped_column(String(2), nullable=False)
    docket_number: Mapped[str] = mapped_column(String(100), nullable=False)
    title: Mapped[Optional[str]] = mapped_column(String(500))
    utility_name: Mapped[Optional[str]] = mapped_column(String(200))
    filing_type: Mapped[Optional[str]] = mapped_column(String(50))
    priority: Mapped[int] = mapped_column(Integer, default=2)  # 1=high, 2=medium, 3=low
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Tracking
    last_checked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_filing_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    filings_count: Mapped[int] = mapped_column(Integer, default=0)
    notes: Mapped[Optional[str]] = mapped_column(String(1000))
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSON)

    # Link to filing records
    regulator_id: Mapped[Optional[int]] = mapped_column(ForeignKey("regulators.id"))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    def __repr__(self) -> str:
        return f"<DocketWatch(state={self.state!r}, docket={self.docket_number!r})>"
