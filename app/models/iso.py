"""ISO and Balancing Authority registry model.

ISOs (7 RTOs) and BAs (~65 non-RTO balancing authorities) are unified into
a single table. BAs within an RTO get parent_iso_id pointing to the RTO.
Independent BAs stand alone with is_rto=False.
"""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import String, Float, Boolean, Integer, JSON, ForeignKey
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

    # BA unification columns
    ba_code: Mapped[Optional[str]] = mapped_column(String(10), unique=True, nullable=True)
        # NULL for pure ISOs (pjm, caiso), set for BAs (BANC, LADWP)
    ba_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    is_rto: Mapped[bool] = mapped_column(Boolean, default=False)
    parent_iso_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("isos.id"), nullable=True)
        # For BAs within an RTO: points to the parent ISO record
    region: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    interconnection: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    rto_neighbor: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    rto_neighbor_secondary: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    interface_points: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    latitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    longitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    transfer_limit_mw: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    transfer_limit_method: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    ba_extra: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Relationships (original)
    zones: Mapped[list["Zone"]] = relationship(back_populates="iso")
    pipeline_runs: Mapped[list["PipelineRun"]] = relationship(back_populates="iso")
    pnodes: Mapped[list["Pnode"]] = relationship(back_populates="iso")
    data_centers: Mapped[list["DataCenter"]] = relationship(back_populates="iso")
    transmission_lines: Mapped[list["TransmissionLine"]] = relationship(back_populates="iso")
    substations: Mapped[list["Substation"]] = relationship(back_populates="iso")

    # BA unification relationships
    parent_iso: Mapped[Optional["ISO"]] = relationship(
        remote_side=[id], back_populates="child_bas")
    child_bas: Mapped[list["ISO"]] = relationship(back_populates="parent_iso")
    ba_hourly_data: Mapped[list["BAHourlyData"]] = relationship(back_populates="iso")
    congestion_scores: Mapped[list["CongestionScore"]] = relationship(back_populates="iso")

    def __repr__(self) -> str:
        if self.ba_code:
            return f"<ISO(ba_code={self.ba_code!r})>"
        return f"<ISO(iso_code={self.iso_code!r})>"


# Avoid circular import at module level
from .zone import Zone  # noqa: E402
from .pipeline_run import PipelineRun  # noqa: E402
from .pnode import Pnode  # noqa: E402
from .data_center import DataCenter  # noqa: E402
from .transmission_line import TransmissionLine  # noqa: E402
from .substation import Substation  # noqa: E402
from .congestion import BAHourlyData, CongestionScore  # noqa: E402
