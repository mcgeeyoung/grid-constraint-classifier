"""Distribution feeder model (feeders off substations)."""

from typing import Optional

from geoalchemy2 import Geometry
from sqlalchemy import Index, String, Float, Integer, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class Feeder(Base):
    __tablename__ = "feeders"
    __table_args__ = (
        Index("ix_feeders_geom", "geom", postgresql_using="gist"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    substation_id: Mapped[int] = mapped_column(ForeignKey("substations.id"), nullable=False)
    feeder_id_external: Mapped[Optional[str]] = mapped_column(String(100))
    capacity_mw: Mapped[Optional[float]] = mapped_column(Float)
    peak_loading_mw: Mapped[Optional[float]] = mapped_column(Float)
    peak_loading_pct: Mapped[Optional[float]] = mapped_column(Float)
    voltage_kv: Mapped[Optional[float]] = mapped_column(Float)
    geometry_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    geom = mapped_column(Geometry("LINESTRING", srid=4326), nullable=True)

    # Relationships
    substation: Mapped["Substation"] = relationship(back_populates="feeders")
    circuits: Mapped[list["Circuit"]] = relationship(back_populates="feeder")

    def __repr__(self) -> str:
        return f"<Feeder(id={self.id}, external={self.feeder_id_external!r})>"


from .substation import Substation  # noqa: E402
from .circuit import Circuit  # noqa: E402
