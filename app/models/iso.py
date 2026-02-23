"""ISO registry model."""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import String, Boolean, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class ISO(Base):
    __tablename__ = "isos"

    id: Mapped[int] = mapped_column(primary_key=True)
    iso_code: Mapped[str] = mapped_column(String(10), unique=True, nullable=False)
    iso_name: Mapped[str] = mapped_column(String(100), nullable=False)
    timezone: Mapped[str] = mapped_column(String(50), nullable=False)
    has_decomposition: Mapped[bool] = mapped_column(Boolean, default=True)
    has_node_pricing: Mapped[bool] = mapped_column(Boolean, default=True)
    config_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    zones: Mapped[list["Zone"]] = relationship(back_populates="iso")
    pipeline_runs: Mapped[list["PipelineRun"]] = relationship(back_populates="iso")
    pnodes: Mapped[list["Pnode"]] = relationship(back_populates="iso")
    data_centers: Mapped[list["DataCenter"]] = relationship(back_populates="iso")

    def __repr__(self) -> str:
        return f"<ISO(iso_code={self.iso_code!r})>"


# Avoid circular import at module level
from .zone import Zone  # noqa: E402
from .pipeline_run import PipelineRun  # noqa: E402
from .pnode import Pnode  # noqa: E402
from .data_center import DataCenter  # noqa: E402
