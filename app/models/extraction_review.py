"""Extraction review queue model for human-in-the-loop verification."""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class ExtractionReview(Base):
    """A queued extraction awaiting human review before promotion to production tables.

    Lifecycle: pending -> approved/rejected/edited
    On approval, records are promoted to GridConstraint/LoadForecast/ResourceNeed.
    """

    __tablename__ = "extraction_reviews"
    __table_args__ = (
        Index("ix_er_status", "review_status"),
        Index("ix_er_type", "extraction_type"),
        Index("ix_er_confidence", "confidence"),
        Index("ix_er_utility", "utility_id"),
        Index("ix_er_filing", "filing_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    utility_id: Mapped[Optional[int]] = mapped_column(ForeignKey("utilities.id"))
    filing_id: Mapped[Optional[int]] = mapped_column(ForeignKey("filings.id"))
    filing_document_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("filing_documents.id"),
    )

    # What was extracted
    extraction_type: Mapped[str] = mapped_column(String(50), nullable=False)
    extracted_data: Mapped[dict] = mapped_column(JSON, nullable=False)
    confidence: Mapped[str] = mapped_column(String(20), nullable=False)

    # Source provenance
    source_file: Mapped[Optional[str]] = mapped_column(String(500))
    raw_text_snippet: Mapped[Optional[str]] = mapped_column(Text)
    source_page: Mapped[Optional[int]] = mapped_column(Integer)
    llm_model: Mapped[Optional[str]] = mapped_column(String(100))
    extraction_notes: Mapped[Optional[str]] = mapped_column(Text)

    # Review state
    review_status: Mapped[str] = mapped_column(
        String(20), default="pending", nullable=False,
    )
    reviewer_notes: Mapped[Optional[str]] = mapped_column(Text)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    promoted_count: Mapped[Optional[int]] = mapped_column(Integer)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    utility: Mapped[Optional["Utility"]] = relationship()
    filing: Mapped[Optional["Filing"]] = relationship()
    filing_document: Mapped[Optional["FilingDocument"]] = relationship()

    def __repr__(self) -> str:
        return (
            f"<ExtractionReview(id={self.id}, type={self.extraction_type!r}, "
            f"status={self.review_status!r}, confidence={self.confidence!r})>"
        )


from .utility import Utility  # noqa: E402
from .filing import Filing, FilingDocument  # noqa: E402
