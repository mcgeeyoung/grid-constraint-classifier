"""Transmission line model (HIFLD data)."""

from typing import Optional

from sqlalchemy import String, Float, Integer, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class TransmissionLine(Base):
    __tablename__ = "transmission_lines"

    id: Mapped[int] = mapped_column(primary_key=True)
    iso_id: Mapped[int] = mapped_column(ForeignKey("isos.id"), nullable=False)
    voltage_kv: Mapped[Optional[int]] = mapped_column(Integer)
    owner: Mapped[Optional[str]] = mapped_column(String(200))
    sub_1: Mapped[Optional[str]] = mapped_column(String(200))
    sub_2: Mapped[Optional[str]] = mapped_column(String(200))
    shape_length: Mapped[Optional[float]] = mapped_column(Float)
    geometry_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Relationships
    iso: Mapped["ISO"] = relationship(back_populates="transmission_lines")

    def __repr__(self) -> str:
        return f"<TransmissionLine(id={self.id}, {self.sub_1}->{self.sub_2}, {self.voltage_kv}kV)>"


from .iso import ISO  # noqa: E402
