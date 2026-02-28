"""Data coverage tracking model.

Tracks completeness and freshness of data across utilities, states, and ISOs
to measure progress toward national coverage. Each record represents the
coverage status for a specific utility or region and data type.
"""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class DataCoverage(Base):
    """Tracks data coverage for a utility/region and data type."""

    __tablename__ = "data_coverage"
    __table_args__ = (
        Index("ix_dc_entity", "entity_type", "entity_id"),
        Index("ix_dc_data_type", "data_type"),
        Index("ix_dc_state", "state"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    # What entity this coverage record is for
    entity_type: Mapped[str] = mapped_column(String(20), nullable=False)
    # entity_type: utility, state, iso, balancing_authority, national
    entity_id: Mapped[Optional[int]] = mapped_column(Integer)
    entity_name: Mapped[str] = mapped_column(String(200), nullable=False)
    state: Mapped[Optional[str]] = mapped_column(String(2))

    # What data type this tracks
    data_type: Mapped[str] = mapped_column(String(50), nullable=False)
    # data_type: load_forecast, grid_constraint, hosting_capacity,
    #   interconnection_queue, transmission_plan, resource_need,
    #   eia_registry, puc_filings, ferc714

    # Coverage metrics
    has_data: Mapped[bool] = mapped_column(default=False)
    record_count: Mapped[int] = mapped_column(Integer, default=0)
    completeness_pct: Mapped[Optional[float]] = mapped_column(Float)
    # completeness_pct: 0-100, measures how complete the data is
    #   e.g., 12/12 months of load data = 100%, 6/12 = 50%

    # Freshness
    latest_data_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_checked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # Data source
    data_source: Mapped[Optional[str]] = mapped_column(String(100))
    # data_source: eia_861, ferc_714, puc_filing, iso_portal, utility_portal, pudl

    # Quality notes
    quality_notes: Mapped[Optional[str]] = mapped_column(String(1000))
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSON)

    # Provenance
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    def __repr__(self) -> str:
        return (
            f"<DataCoverage({self.entity_type}:{self.entity_name}, "
            f"type={self.data_type}, has_data={self.has_data})>"
        )
