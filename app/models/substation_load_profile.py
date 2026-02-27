"""Substation hourly load profile model (PG&E GRIP data)."""

from sqlalchemy import Float, SmallInteger, Integer, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class SubstationLoadProfile(Base):
    __tablename__ = "substation_load_profiles"
    __table_args__ = (
        UniqueConstraint("substation_id", "month", "hour", name="uq_sub_load_profile"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    substation_id: Mapped[int] = mapped_column(ForeignKey("substations.id"), nullable=False)
    month: Mapped[int] = mapped_column(SmallInteger, nullable=False)  # 1-12
    hour: Mapped[int] = mapped_column(SmallInteger, nullable=False)   # 0-23
    load_low_kw: Mapped[float] = mapped_column(Float, nullable=False)
    load_high_kw: Mapped[float] = mapped_column(Float, nullable=False)

    # Relationships
    substation: Mapped["Substation"] = relationship(back_populates="load_profiles")

    def __repr__(self) -> str:
        return f"<SubstationLoadProfile(sub={self.substation_id}, m={self.month}, h={self.hour})>"


from .substation import Substation  # noqa: E402
