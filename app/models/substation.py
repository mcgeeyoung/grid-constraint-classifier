"""Substation model (GRIP data)."""

from typing import Optional

from geoalchemy2 import Geometry
from sqlalchemy import Index, String, Float, Integer, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class Substation(Base):
    __tablename__ = "substations"
    __table_args__ = (
        UniqueConstraint("iso_id", "substation_name", "bank_name", name="uq_substations"),
        Index("ix_substations_iso_id", "iso_id"),
        Index("ix_substations_zone_id", "zone_id"),
        Index("ix_substations_peak_loading_pct", "peak_loading_pct"),
        Index("ix_substations_geom", "geom", postgresql_using="gist"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    iso_id: Mapped[int] = mapped_column(ForeignKey("isos.id"), nullable=False)
    zone_id: Mapped[Optional[int]] = mapped_column(ForeignKey("zones.id"), nullable=True)
    nearest_pnode_id: Mapped[Optional[int]] = mapped_column(ForeignKey("pnodes.id"), nullable=True)
    substation_name: Mapped[str] = mapped_column(String(200), nullable=False)
    bank_name: Mapped[Optional[str]] = mapped_column(String(200))
    division: Mapped[Optional[str]] = mapped_column(String(100))
    facility_rating_mw: Mapped[Optional[float]] = mapped_column(Float)
    facility_loading_mw: Mapped[Optional[float]] = mapped_column(Float)
    peak_loading_pct: Mapped[Optional[float]] = mapped_column(Float)
    facility_type: Mapped[Optional[str]] = mapped_column(String(50))
    lat: Mapped[Optional[float]] = mapped_column(Float)
    lon: Mapped[Optional[float]] = mapped_column(Float)
    geom = mapped_column(Geometry("POINT", srid=4326), nullable=True)

    # Relationships
    iso: Mapped["ISO"] = relationship(back_populates="substations")
    zone: Mapped[Optional["Zone"]] = relationship(back_populates="substations")
    nearest_pnode: Mapped[Optional["Pnode"]] = relationship()
    feeders: Mapped[list["Feeder"]] = relationship(back_populates="substation")
    load_profiles: Mapped[list["SubstationLoadProfile"]] = relationship(back_populates="substation")

    def __repr__(self) -> str:
        return f"<Substation(name={self.substation_name!r}, rating={self.facility_rating_mw}MW)>"


from .iso import ISO  # noqa: E402
from .zone import Zone  # noqa: E402
from .pnode import Pnode  # noqa: E402
from .feeder import Feeder  # noqa: E402
from .substation_load_profile import SubstationLoadProfile  # noqa: E402
