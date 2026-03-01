"""Interconnection queue model for tracking DER/generation interconnection requests.

Data sources include LBNL Queues dataset, individual utility queue downloads,
and ISO/RTO queue portals.
"""

from datetime import date, datetime, timezone
from typing import Optional

from geoalchemy2 import Geometry
from sqlalchemy import Date, DateTime, Float, ForeignKey, Index, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class InterconnectionQueue(Base):
    """A single interconnection request from a utility or ISO queue."""

    __tablename__ = "interconnection_queue"
    __table_args__ = (
        Index("ix_iq_utility", "utility_id"),
        Index("ix_iq_status", "queue_status"),
        Index("ix_iq_type", "generation_type"),
        Index("ix_iq_state", "state"),
        Index("ix_iq_geom", "geom", postgresql_using="gist"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    utility_id: Mapped[Optional[int]] = mapped_column(ForeignKey("utilities.id"))
    iso_id: Mapped[Optional[int]] = mapped_column(ForeignKey("isos.id"))

    # Queue identification
    queue_id: Mapped[str] = mapped_column(String(100), nullable=False)
    project_name: Mapped[Optional[str]] = mapped_column(String(500))

    # Location
    state: Mapped[Optional[str]] = mapped_column(String(2))
    county: Mapped[Optional[str]] = mapped_column(String(100))
    point_of_interconnection: Mapped[Optional[str]] = mapped_column(String(300))
    geom = mapped_column(Geometry("POINT", srid=4326), nullable=True, deferred=True)
    latitude: Mapped[Optional[float]] = mapped_column(Float)
    longitude: Mapped[Optional[float]] = mapped_column(Float)

    # Project details
    generation_type: Mapped[Optional[str]] = mapped_column(String(50))  # solar, wind, storage, hybrid, gas, etc.
    fuel_type: Mapped[Optional[str]] = mapped_column(String(50))
    capacity_mw: Mapped[Optional[float]] = mapped_column(Float)
    capacity_mw_storage: Mapped[Optional[float]] = mapped_column(Float)  # for hybrid projects

    # Queue status and dates
    queue_status: Mapped[Optional[str]] = mapped_column(String(50))  # active, withdrawn, completed, suspended
    date_entered: Mapped[Optional[date]] = mapped_column(Date)
    date_completed: Mapped[Optional[date]] = mapped_column(Date)
    date_withdrawn: Mapped[Optional[date]] = mapped_column(Date)
    proposed_online_date: Mapped[Optional[date]] = mapped_column(Date)

    # Study phase
    study_phase: Mapped[Optional[str]] = mapped_column(String(50))  # feasibility, system_impact, facilities

    # Interconnection details
    voltage_kv: Mapped[Optional[float]] = mapped_column(Float)
    substation_name: Mapped[Optional[str]] = mapped_column(String(300))

    # Data source
    data_source: Mapped[str] = mapped_column(String(50), nullable=False)  # lbnl, utility_direct, iso_portal
    source_url: Mapped[Optional[str]] = mapped_column(String(1000))
    raw_data: Mapped[Optional[dict]] = mapped_column(JSON)

    # Provenance
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    utility: Mapped[Optional["Utility"]] = relationship()
    iso: Mapped[Optional["ISO"]] = relationship()

    def __repr__(self) -> str:
        return (
            f"<InterconnectionQueue(queue_id={self.queue_id!r}, "
            f"type={self.generation_type!r}, mw={self.capacity_mw})>"
        )


from .utility import Utility  # noqa: E402
from .iso import ISO  # noqa: E402
