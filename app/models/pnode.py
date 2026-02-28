"""Pnode (pricing node) model."""

from typing import Optional

from geoalchemy2 import Geometry
from sqlalchemy import Index, String, Float, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class Pnode(Base):
    __tablename__ = "pnodes"
    __table_args__ = (
        UniqueConstraint("iso_id", "node_id_external", name="uq_pnodes_iso_node"),
        Index("ix_pnodes_iso_id", "iso_id"),
        Index("ix_pnodes_zone_id", "zone_id"),
        Index("ix_pnodes_geom", "geom", postgresql_using="gist"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    iso_id: Mapped[int] = mapped_column(ForeignKey("isos.id"))
    zone_id: Mapped[Optional[int]] = mapped_column(ForeignKey("zones.id"), nullable=True)
    node_id_external: Mapped[str] = mapped_column(String(50), nullable=False)
    node_name: Mapped[Optional[str]] = mapped_column(String(100))
    lat: Mapped[Optional[float]] = mapped_column(Float)
    lon: Mapped[Optional[float]] = mapped_column(Float)
    geom = mapped_column(Geometry("POINT", srid=4326), nullable=True)

    # Relationships
    iso: Mapped["ISO"] = relationship(back_populates="pnodes")
    zone: Mapped["Zone"] = relationship(back_populates="pnodes")
    scores: Mapped[list["PnodeScore"]] = relationship(back_populates="pnode")

    def __repr__(self) -> str:
        return f"<Pnode(node_name={self.node_name!r})>"


from .iso import ISO  # noqa: E402
from .zone import Zone  # noqa: E402
from .pnode_score import PnodeScore  # noqa: E402
