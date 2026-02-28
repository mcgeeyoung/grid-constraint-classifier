"""Data center model."""

from datetime import datetime
from typing import Optional

from geoalchemy2 import Geometry
from sqlalchemy import Index, String, Float, ForeignKey, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class DataCenter(Base):
    __tablename__ = "data_centers"
    __table_args__ = (
        Index("ix_data_centers_iso_id", "iso_id"),
        Index("ix_data_centers_zone_id", "zone_id"),
        Index("ix_data_centers_status", "status"),
        Index("ix_data_centers_geom", "geom", postgresql_using="gist"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    iso_id: Mapped[int] = mapped_column(ForeignKey("isos.id"))
    zone_id: Mapped[Optional[int]] = mapped_column(ForeignKey("zones.id"), nullable=True)
    external_slug: Mapped[Optional[str]] = mapped_column(String(200), unique=True)
    facility_name: Mapped[Optional[str]] = mapped_column(String(200))
    status: Mapped[Optional[str]] = mapped_column(String(30))
    capacity_mw: Mapped[Optional[float]] = mapped_column(Float)
    lat: Mapped[Optional[float]] = mapped_column(Float)
    lon: Mapped[Optional[float]] = mapped_column(Float)
    geom = mapped_column(Geometry("POINT", srid=4326), nullable=True)
    state_code: Mapped[Optional[str]] = mapped_column(String(5))
    county: Mapped[Optional[str]] = mapped_column(String(100))
    operator: Mapped[Optional[str]] = mapped_column(String(200))
    scraped_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # Relationships
    iso: Mapped["ISO"] = relationship(back_populates="data_centers")
    zone: Mapped["Zone"] = relationship(back_populates="data_centers")

    def __repr__(self) -> str:
        return f"<DataCenter(facility_name={self.facility_name!r})>"


from .iso import ISO  # noqa: E402
from .zone import Zone  # noqa: E402
