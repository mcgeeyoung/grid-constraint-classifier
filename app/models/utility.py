"""Utility registry model for hosting capacity and data pipeline."""

from datetime import datetime
from typing import Optional

from sqlalchemy import Integer, String, Boolean, ForeignKey, DateTime, JSON, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class Utility(Base):
    __tablename__ = "utilities"
    __table_args__ = (
        Index("ix_utilities_iso_id", "iso_id"),
        Index("ix_utilities_eia_id", "eia_id"),
        Index("ix_utilities_regulator_id", "regulator_id"),
        Index("ix_utilities_state", "state"),
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

    # DP-0: EIA-861 utility registry fields
    eia_id: Mapped[Optional[int]] = mapped_column(Integer, unique=True)
    utility_type: Mapped[Optional[str]] = mapped_column(String(30))  # IOU, cooperative, municipal, federal, political_subdivision, retail_power_marketer
    state: Mapped[Optional[str]] = mapped_column(String(2))  # primary state
    regulator_id: Mapped[Optional[int]] = mapped_column(ForeignKey("regulators.id"))
    customers_total: Mapped[Optional[int]] = mapped_column(Integer)
    sales_mwh: Mapped[Optional[float]] = mapped_column()
    service_territory_counties: Mapped[Optional[list]] = mapped_column(JSON)

    # Relationships
    iso: Mapped[Optional["ISO"]] = relationship()
    regulator: Mapped[Optional["Regulator"]] = relationship(back_populates="utilities")
    hosting_capacity_records: Mapped[list["HostingCapacityRecord"]] = relationship(back_populates="utility")
    ingestion_runs: Mapped[list["HCIngestionRun"]] = relationship(back_populates="utility")
    filings: Mapped[list["Filing"]] = relationship(back_populates="utility")

    def __repr__(self) -> str:
        return f"<Utility(code={self.utility_code!r}, name={self.utility_name!r})>"


from .iso import ISO  # noqa: E402
from .regulator import Regulator  # noqa: E402
from .hosting_capacity import HostingCapacityRecord, HCIngestionRun  # noqa: E402
from .filing import Filing  # noqa: E402
