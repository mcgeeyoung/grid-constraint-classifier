"""Utility registry model for hosting capacity data sources."""

from datetime import datetime
from typing import Optional

from sqlalchemy import String, Boolean, ForeignKey, DateTime, JSON, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class Utility(Base):
    __tablename__ = "utilities"
    __table_args__ = (
        Index("ix_utilities_iso_id", "iso_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    utility_code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    utility_name: Mapped[str] = mapped_column(String(200), nullable=False)
    parent_company: Mapped[Optional[str]] = mapped_column(String(200))
    iso_id: Mapped[Optional[int]] = mapped_column(ForeignKey("isos.id"))
    states: Mapped[Optional[list]] = mapped_column(JSON)
    data_source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    requires_auth: Mapped[bool] = mapped_column(Boolean, default=False)
    service_url: Mapped[Optional[str]] = mapped_column(String(500))
    last_ingested_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    config_json: Mapped[Optional[dict]] = mapped_column(JSON)

    # Relationships
    iso: Mapped[Optional["ISO"]] = relationship()
    hosting_capacity_records: Mapped[list["HostingCapacityRecord"]] = relationship(back_populates="utility")
    ingestion_runs: Mapped[list["HCIngestionRun"]] = relationship(back_populates="utility")

    def __repr__(self) -> str:
        return f"<Utility(code={self.utility_code!r}, name={self.utility_name!r})>"


from .iso import ISO  # noqa: E402
from .hosting_capacity import HostingCapacityRecord, HCIngestionRun  # noqa: E402
