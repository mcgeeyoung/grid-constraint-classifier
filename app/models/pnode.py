"""Pnode (pricing node) model."""

from typing import Optional

from sqlalchemy import String, Float, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class Pnode(Base):
    __tablename__ = "pnodes"
    __table_args__ = (
        UniqueConstraint("iso_id", "node_id_external", name="uq_pnodes_iso_node"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    iso_id: Mapped[int] = mapped_column(ForeignKey("isos.id"))
    zone_id: Mapped[Optional[int]] = mapped_column(ForeignKey("zones.id"), nullable=True)
    node_id_external: Mapped[str] = mapped_column(String(50), nullable=False)
    node_name: Mapped[Optional[str]] = mapped_column(String(100))
    lat: Mapped[Optional[float]] = mapped_column(Float)
    lon: Mapped[Optional[float]] = mapped_column(Float)

    # Relationships
    iso: Mapped["ISO"] = relationship(back_populates="pnodes")
    zone: Mapped["Zone"] = relationship(back_populates="pnodes")
    scores: Mapped[list["PnodeScore"]] = relationship(back_populates="pnode")

    def __repr__(self) -> str:
        return f"<Pnode(node_name={self.node_name!r})>"


from .iso import ISO  # noqa: E402
from .zone import Zone  # noqa: E402
from .pnode_score import PnodeScore  # noqa: E402
