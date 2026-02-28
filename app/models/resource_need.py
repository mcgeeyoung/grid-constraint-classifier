"""Resource need model for extracted procurement/capacity requirement data."""

from typing import Optional

from sqlalchemy import Float, ForeignKey, Index, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class ResourceNeed(Base):
    """A resource need (capacity, energy, flexibility) from a regulatory filing."""

    __tablename__ = "resource_needs"
    __table_args__ = (
        Index("ix_rn_utility", "utility_id"),
        Index("ix_rn_filing", "filing_id"),
        Index("ix_rn_year", "need_year"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    utility_id: Mapped[int] = mapped_column(ForeignKey("utilities.id"), nullable=False)
    filing_id: Mapped[Optional[int]] = mapped_column(ForeignKey("filings.id"))

    need_type: Mapped[str] = mapped_column(String(50), nullable=False)
    need_mw: Mapped[Optional[float]] = mapped_column(Float)
    need_year: Mapped[Optional[int]] = mapped_column(Integer)
    location_type: Mapped[Optional[str]] = mapped_column(String(50))
    location_name: Mapped[Optional[str]] = mapped_column(String(200))
    eligible_resource_types: Mapped[Optional[list]] = mapped_column(JSON)
    notes: Mapped[Optional[str]] = mapped_column(String(1000))

    # Relationships
    utility: Mapped["Utility"] = relationship()
    filing: Mapped[Optional["Filing"]] = relationship(back_populates="resource_needs")

    def __repr__(self) -> str:
        return (
            f"<ResourceNeed(type={self.need_type!r}, "
            f"mw={self.need_mw}, year={self.need_year})>"
        )


from .utility import Utility  # noqa: E402
from .filing import Filing  # noqa: E402
