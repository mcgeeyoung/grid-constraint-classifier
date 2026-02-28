"""Grid constraint model for extracted infrastructure constraint data."""

from typing import Optional

from geoalchemy2 import Geometry
from sqlalchemy import Float, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class GridConstraint(Base):
    """An infrastructure constraint extracted from a regulatory filing."""

    __tablename__ = "grid_constraints"
    __table_args__ = (
        Index("ix_gc_utility", "utility_id"),
        Index("ix_gc_filing", "filing_id"),
        Index("ix_gc_type", "constraint_type"),
        Index("ix_gc_geom", "location_geom", postgresql_using="gist"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    utility_id: Mapped[int] = mapped_column(ForeignKey("utilities.id"), nullable=False)
    filing_id: Mapped[Optional[int]] = mapped_column(ForeignKey("filings.id"))

    constraint_type: Mapped[str] = mapped_column(String(50), nullable=False)
    location_type: Mapped[Optional[str]] = mapped_column(String(50))
    location_name: Mapped[Optional[str]] = mapped_column(String(300))
    location_geom = mapped_column(Geometry("POINT", srid=4326), nullable=True)

    current_capacity_mw: Mapped[Optional[float]] = mapped_column(Float)
    forecasted_load_mw: Mapped[Optional[float]] = mapped_column(Float)
    constraint_year: Mapped[Optional[int]] = mapped_column(Integer)
    headroom_mw: Mapped[Optional[float]] = mapped_column(Float)

    notes: Mapped[Optional[str]] = mapped_column(String(1000))
    raw_source_reference: Mapped[Optional[str]] = mapped_column(String(300))
    confidence: Mapped[Optional[str]] = mapped_column(String(20))

    # Relationships
    utility: Mapped["Utility"] = relationship()
    filing: Mapped[Optional["Filing"]] = relationship(back_populates="grid_constraints")

    def __repr__(self) -> str:
        return (
            f"<GridConstraint(type={self.constraint_type!r}, "
            f"location={self.location_name!r})>"
        )


from .utility import Utility  # noqa: E402
from .filing import Filing  # noqa: E402
