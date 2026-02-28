"""Load forecast model for extracted demand projection data."""

from typing import Optional

from sqlalchemy import Float, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class LoadForecast(Base):
    """A load forecast data point extracted from a regulatory filing."""

    __tablename__ = "load_forecasts"
    __table_args__ = (
        Index("ix_lf_utility", "utility_id"),
        Index("ix_lf_filing", "filing_id"),
        Index("ix_lf_year", "forecast_year"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    utility_id: Mapped[int] = mapped_column(ForeignKey("utilities.id"), nullable=False)
    filing_id: Mapped[Optional[int]] = mapped_column(ForeignKey("filings.id"))

    forecast_year: Mapped[int] = mapped_column(Integer, nullable=False)
    area_name: Mapped[Optional[str]] = mapped_column(String(200))
    area_type: Mapped[Optional[str]] = mapped_column(String(50))

    peak_demand_mw: Mapped[Optional[float]] = mapped_column(Float)
    energy_gwh: Mapped[Optional[float]] = mapped_column(Float)
    growth_rate_pct: Mapped[Optional[float]] = mapped_column(Float)
    scenario: Mapped[Optional[str]] = mapped_column(String(30))

    # Relationships
    utility: Mapped["Utility"] = relationship()
    filing: Mapped[Optional["Filing"]] = relationship(back_populates="load_forecasts")

    def __repr__(self) -> str:
        return (
            f"<LoadForecast(utility_id={self.utility_id}, "
            f"year={self.forecast_year}, area={self.area_name!r})>"
        )


from .utility import Utility  # noqa: E402
from .filing import Filing  # noqa: E402
