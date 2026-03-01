"""Zone model (zones within an ISO)."""

from typing import Optional

from geoalchemy2 import Geometry
from sqlalchemy import Index, String, Float, ForeignKey, UniqueConstraint, ARRAY, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class Zone(Base):
    __tablename__ = "zones"
    __table_args__ = (
        UniqueConstraint("iso_id", "zone_code", name="uq_zones_iso_zone"),
        Index("ix_zones_boundary_geom", "boundary_geom", postgresql_using="gist"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    iso_id: Mapped[int] = mapped_column(ForeignKey("isos.id"))
    zone_code: Mapped[str] = mapped_column(String(50), nullable=False)
    zone_name: Mapped[Optional[str]] = mapped_column(String(100))
    centroid_lat: Mapped[Optional[float]] = mapped_column(Float)
    centroid_lon: Mapped[Optional[float]] = mapped_column(Float)
    states: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    boundary_geojson: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    boundary_geom = mapped_column(Geometry("MULTIPOLYGON", srid=4326), nullable=True, deferred=True)

    # Relationships
    iso: Mapped["ISO"] = relationship(back_populates="zones")
    zone_lmps: Mapped[list["ZoneLMP"]] = relationship(back_populates="zone")
    classifications: Mapped[list["ZoneClassification"]] = relationship(back_populates="zone")
    pnodes: Mapped[list["Pnode"]] = relationship(back_populates="zone")
    data_centers: Mapped[list["DataCenter"]] = relationship(back_populates="zone")
    der_recommendations: Mapped[list["DERRecommendation"]] = relationship(back_populates="zone")
    substations: Mapped[list["Substation"]] = relationship(back_populates="zone")

    def __repr__(self) -> str:
        return f"<Zone(zone_code={self.zone_code!r})>"


from .iso import ISO  # noqa: E402
from .zone_lmp import ZoneLMP  # noqa: E402
from .zone_classification import ZoneClassification  # noqa: E402
from .pnode import Pnode  # noqa: E402
from .data_center import DataCenter  # noqa: E402
from .der_recommendation import DERRecommendation  # noqa: E402
from .substation import Substation  # noqa: E402
