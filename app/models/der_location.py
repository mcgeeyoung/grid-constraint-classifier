"""DER location model (physical or hypothetical DER placements)."""

from typing import Optional

from geoalchemy2 import Geometry
from sqlalchemy import Index, String, Float, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class DERLocation(Base):
    __tablename__ = "der_locations"
    __table_args__ = (
        Index("ix_der_locations_iso_id", "iso_id"),
        Index("ix_der_locations_zone_id", "zone_id"),
        Index("ix_der_locations_source", "source"),
        Index("ix_der_locations_wattcarbon_asset_id", "wattcarbon_asset_id"),
        Index("ix_der_locations_geom", "geom", postgresql_using="gist"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    iso_id: Mapped[int] = mapped_column(ForeignKey("isos.id"), nullable=False)
    zone_id: Mapped[Optional[int]] = mapped_column(ForeignKey("zones.id"), nullable=True)
    substation_id: Mapped[Optional[int]] = mapped_column(ForeignKey("substations.id"), nullable=True)
    feeder_id: Mapped[Optional[int]] = mapped_column(ForeignKey("feeders.id"), nullable=True)
    circuit_id: Mapped[Optional[int]] = mapped_column(ForeignKey("circuits.id"), nullable=True)
    nearest_pnode_id: Mapped[Optional[int]] = mapped_column(ForeignKey("pnodes.id"), nullable=True)
    der_type: Mapped[str] = mapped_column(String(50), nullable=False)
    eac_category: Mapped[Optional[str]] = mapped_column(String(30))
    capacity_mw: Mapped[float] = mapped_column(Float, nullable=False)
    lat: Mapped[Optional[float]] = mapped_column(Float)
    lon: Mapped[Optional[float]] = mapped_column(Float)
    geom = mapped_column(Geometry("POINT", srid=4326), nullable=True)
    wattcarbon_asset_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    source: Mapped[str] = mapped_column(String(30), nullable=False, default="hypothetical")

    # Relationships
    iso: Mapped["ISO"] = relationship()
    zone: Mapped[Optional["Zone"]] = relationship()
    substation: Mapped[Optional["Substation"]] = relationship()
    feeder: Mapped[Optional["Feeder"]] = relationship()
    circuit: Mapped[Optional["Circuit"]] = relationship()
    nearest_pnode: Mapped[Optional["Pnode"]] = relationship()
    valuations: Mapped[list["DERValuation"]] = relationship(back_populates="der_location")

    def __repr__(self) -> str:
        return f"<DERLocation(id={self.id}, type={self.der_type!r}, capacity={self.capacity_mw}MW)>"


from .iso import ISO  # noqa: E402
from .zone import Zone  # noqa: E402
from .substation import Substation  # noqa: E402
from .feeder import Feeder  # noqa: E402
from .circuit import Circuit  # noqa: E402
from .pnode import Pnode  # noqa: E402
from .der_valuation import DERValuation  # noqa: E402
