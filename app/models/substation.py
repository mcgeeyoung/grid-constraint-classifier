"""Substation model (GRIP data)."""

from typing import Optional

from sqlalchemy import String, Float, Integer, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class Substation(Base):
    __tablename__ = "substations"
    __table_args__ = (
        UniqueConstraint("iso_id", "substation_name", "bank_name", name="uq_substations"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    iso_id: Mapped[int] = mapped_column(ForeignKey("isos.id"), nullable=False)
    substation_name: Mapped[str] = mapped_column(String(200), nullable=False)
    bank_name: Mapped[Optional[str]] = mapped_column(String(200))
    division: Mapped[Optional[str]] = mapped_column(String(100))
    facility_rating_mw: Mapped[Optional[float]] = mapped_column(Float)
    facility_loading_mw: Mapped[Optional[float]] = mapped_column(Float)
    peak_loading_pct: Mapped[Optional[float]] = mapped_column(Float)
    facility_type: Mapped[Optional[str]] = mapped_column(String(50))
    lat: Mapped[Optional[float]] = mapped_column(Float)
    lon: Mapped[Optional[float]] = mapped_column(Float)

    # Relationships
    iso: Mapped["ISO"] = relationship(back_populates="substations")

    def __repr__(self) -> str:
        return f"<Substation(name={self.substation_name!r}, rating={self.facility_rating_mw}MW)>"


from .iso import ISO  # noqa: E402
