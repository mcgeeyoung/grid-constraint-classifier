"""State public utility commission (PUC) registry model."""

from typing import Optional

from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class Regulator(Base):
    """A state-level regulatory body (PUC/PSC) that oversees electric utilities."""

    __tablename__ = "regulators"

    id: Mapped[int] = mapped_column(primary_key=True)
    state: Mapped[str] = mapped_column(String(2), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    abbreviation: Mapped[Optional[str]] = mapped_column(String(20))
    website: Mapped[Optional[str]] = mapped_column(String(500))
    efiling_url: Mapped[Optional[str]] = mapped_column(String(500))
    efiling_type: Mapped[Optional[str]] = mapped_column(String(50))
    api_available: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[Optional[str]] = mapped_column(String(1000))

    # Relationships
    utilities: Mapped[list["Utility"]] = relationship(back_populates="regulator")
    filings: Mapped[list["Filing"]] = relationship(back_populates="regulator")

    def __repr__(self) -> str:
        return f"<Regulator(state={self.state!r}, name={self.name!r})>"


from .utility import Utility  # noqa: E402
from .filing import Filing  # noqa: E402
