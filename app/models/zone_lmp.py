"""Zone-level LMP time series model.

The zone_lmps table is LIST-partitioned by iso_id in PostgreSQL.
Each ISO gets its own physical partition (zone_lmps_iso_1, zone_lmps_iso_2, etc.)
for efficient per-ISO queries. The composite primary key (id, iso_id) is required
by PostgreSQL partitioning.

Pre-computed aggregations are available via materialized views:
  - zone_lmp_hourly_avg: per iso/zone/hour/month aggregates
  - zone_lmp_hourly_avg_annual: per iso/zone/hour aggregates (all months)
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import Float, SmallInteger, ForeignKey, UniqueConstraint, DateTime, Index, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class ZoneLMP(Base):
    __tablename__ = "zone_lmps"
    __table_args__ = (
        UniqueConstraint("iso_id", "zone_id", "timestamp_utc", name="uq_zone_lmps"),
        Index("ix_zone_lmps_iso_id", "iso_id"),
        Index("ix_zone_lmps_zone_id", "zone_id"),
        Index("ix_zone_lmps_timestamp_utc", "timestamp_utc"),
        Index("ix_zone_lmps_iso_zone_ts", "iso_id", "zone_id", "timestamp_utc"),
        Index("ix_zone_lmps_hour_local", "hour_local"),
        Index("ix_zone_lmps_month", "month"),
        # PostgreSQL list partitioning requires partition key in PK
        {"postgresql_partition_by": "LIST (iso_id)"},
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    iso_id: Mapped[int] = mapped_column(ForeignKey("isos.id"), primary_key=True)
    zone_id: Mapped[int] = mapped_column(ForeignKey("zones.id"), nullable=False)
    timestamp_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    lmp: Mapped[float] = mapped_column(Float, nullable=False)
    energy: Mapped[Optional[float]] = mapped_column(Float)
    congestion: Mapped[Optional[float]] = mapped_column(Float)
    loss: Mapped[Optional[float]] = mapped_column(Float)
    hour_local: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    month: Mapped[int] = mapped_column(SmallInteger, nullable=False)

    # Relationships
    zone: Mapped["Zone"] = relationship(back_populates="zone_lmps")

    def __repr__(self) -> str:
        return f"<ZoneLMP(zone_id={self.zone_id}, ts={self.timestamp_utc})>"


from .zone import Zone  # noqa: E402
