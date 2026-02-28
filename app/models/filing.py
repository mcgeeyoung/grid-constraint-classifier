"""Filing and filing document models for regulatory docket tracking."""

from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy import Date, DateTime, ForeignKey, Index, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class Filing(Base):
    """A regulatory filing (IRP, DRP, rate case, etc.) tracked by docket number."""

    __tablename__ = "filings"
    __table_args__ = (
        Index("ix_filings_utility", "utility_id"),
        Index("ix_filings_regulator", "regulator_id"),
        Index("ix_filings_docket", "docket_number"),
        Index("ix_filings_type", "filing_type"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    utility_id: Mapped[int] = mapped_column(ForeignKey("utilities.id"), nullable=False)
    regulator_id: Mapped[Optional[int]] = mapped_column(ForeignKey("regulators.id"))
    docket_number: Mapped[Optional[str]] = mapped_column(String(100))
    filing_type: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[Optional[str]] = mapped_column(String(500))
    filed_date: Mapped[Optional[date]] = mapped_column(Date)
    source_url: Mapped[Optional[str]] = mapped_column(String(1000))
    raw_document_path: Mapped[Optional[str]] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(30), default="discovered")
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    utility: Mapped["Utility"] = relationship(back_populates="filings")
    regulator: Mapped[Optional["Regulator"]] = relationship(back_populates="filings")
    documents: Mapped[list["FilingDocument"]] = relationship(back_populates="filing")
    grid_constraints: Mapped[list["GridConstraint"]] = relationship(back_populates="filing")
    load_forecasts: Mapped[list["LoadForecast"]] = relationship(back_populates="filing")
    resource_needs: Mapped[list["ResourceNeed"]] = relationship(back_populates="filing")

    def __repr__(self) -> str:
        return f"<Filing(docket={self.docket_number!r}, type={self.filing_type!r})>"


class FilingDocument(Base):
    """An individual document within a regulatory filing."""

    __tablename__ = "filing_documents"
    __table_args__ = (
        Index("ix_filing_docs_filing", "filing_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    filing_id: Mapped[int] = mapped_column(ForeignKey("filings.id"), nullable=False)
    document_type: Mapped[Optional[str]] = mapped_column(String(50))
    filename: Mapped[Optional[str]] = mapped_column(String(300))
    mime_type: Mapped[Optional[str]] = mapped_column(String(100))
    raw_path: Mapped[Optional[str]] = mapped_column(String(500))
    extracted_text: Mapped[Optional[str]] = mapped_column(Text)
    parsed_data: Mapped[Optional[dict]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(30), default="pending")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    filing: Mapped["Filing"] = relationship(back_populates="documents")

    def __repr__(self) -> str:
        return f"<FilingDocument(filing_id={self.filing_id}, type={self.document_type!r})>"


from .utility import Utility  # noqa: E402
from .regulator import Regulator  # noqa: E402
from .grid_constraint import GridConstraint  # noqa: E402
from .load_forecast import LoadForecast  # noqa: E402
from .resource_need import ResourceNeed  # noqa: E402
