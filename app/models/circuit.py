"""Circuit model (lateral branches off feeders)."""

from typing import Optional

from sqlalchemy import String, Float, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class Circuit(Base):
    __tablename__ = "circuits"

    id: Mapped[int] = mapped_column(primary_key=True)
    feeder_id: Mapped[int] = mapped_column(ForeignKey("feeders.id"), nullable=False)
    circuit_id_external: Mapped[Optional[str]] = mapped_column(String(100))
    capacity_mw: Mapped[Optional[float]] = mapped_column(Float)
    peak_loading_mw: Mapped[Optional[float]] = mapped_column(Float)
    lat: Mapped[Optional[float]] = mapped_column(Float)
    lon: Mapped[Optional[float]] = mapped_column(Float)

    # Relationships
    feeder: Mapped["Feeder"] = relationship(back_populates="circuits")

    def __repr__(self) -> str:
        return f"<Circuit(id={self.id}, external={self.circuit_id_external!r})>"


from .feeder import Feeder  # noqa: E402
