"""Pydantic models for Dominion DER demo API."""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field

from dominion_dispatch.config import (
    DISPATCH_EXTREME_ABS_QUANTILE_DEFAULT,
    DISPATCH_STRESSED_ABS_USD_DEFAULT,
    DISPATCH_STRESSED_SIGNAL_FRACTION_DEFAULT,
)


class DominionIngestionRunResponse(BaseModel):
    id: int
    operating_date: date
    zone_code: str
    lmp_type: str
    status: str
    retrieved_at_utc: datetime
    row_count: Optional[int] = None
    error_message: Optional[str] = None
    idempotency_key: Optional[str] = None

    class Config:
        from_attributes = True


class DominionIngestRequest(BaseModel):
    operating_date: date = Field(..., description="DA operating day in EPT calendar")
    replace_existing: bool = False
    zone_code: str = Field(default="DOM", max_length=20)
    lmp_type: str = Field(default="LOAD", max_length=20)


class DominionDeviceResponse(BaseModel):
    device_id_external: str
    pjm_load_zone_code: str
    primary_pnode_id: str
    primary_pnode_name: Optional[str] = None
    asset_lat: Optional[float] = None
    asset_lon: Optional[float] = None
    asset_display_name: Optional[str] = None
    listed_capacity_kw: Optional[float] = None
    effective_from: date
    effective_to: Optional[date] = None

    class Config:
        from_attributes = True


class DominionDispatchHourResponse(BaseModel):
    device_id_external: str
    primary_pnode_id: str
    interval_start_utc: datetime
    raw_congestion: Optional[float] = None
    resolved_congestion: Optional[float] = None
    resolution_strategy: str
    dispatch_signal: Optional[float] = None
    extreme_abs_threshold_usd: Optional[float] = None
    period_tier: Optional[str] = None
    dispatch_mandatory: Optional[bool] = None
    dispatch_signal_program: Optional[float] = None

    class Config:
        from_attributes = True


class DominionDispatchRebuildRequest(BaseModel):
    ingestion_run_id: int
    replace_existing: bool = True
    no_period_policy: bool = False
    stressed_threshold_usd: float = Field(
        default=DISPATCH_STRESSED_ABS_USD_DEFAULT, ge=0.0
    )
    extreme_quantile: float = Field(
        default=DISPATCH_EXTREME_ABS_QUANTILE_DEFAULT, gt=0.0, lt=1.0
    )
    stressed_signal_fraction: float = Field(
        default=DISPATCH_STRESSED_SIGNAL_FRACTION_DEFAULT, ge=0.0, le=1.0
    )
    stressed_peak_only: bool = False


class DominionDispatchRebuildResponse(BaseModel):
    ingestion_run_id: int
    rows_persisted: int
    device_count: int


class DominionParticipationRow(BaseModel):
    device_id_external: str
    primary_pnode_id: Optional[str] = None
    primary_pnode_name: Optional[str] = None
    asset_display_name: Optional[str] = None
    runs: int
    total_hours: int
    normal_hours: int
    stressed_hours: int
    extreme_hours: int
    mandatory_hours: int
    any_dispatch_hours: int
    participation_pct: float
    mandatory_pct: float
    window_start: Optional[date] = None
    window_end: Optional[date] = None


class DominionParticipationResponse(BaseModel):
    window_days: int
    window_start: Optional[date] = None
    window_end: Optional[date] = None
    runs: int
    devices: list[DominionParticipationRow]
