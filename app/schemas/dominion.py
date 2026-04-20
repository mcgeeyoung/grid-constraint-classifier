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


# ───────────────────────── admin dashboard ─────────────────────────


class AdminZoneSummary(BaseModel):
    id: str
    label: str
    description: str
    pnode_ids: list[str]
    device_ids: list[str]
    device_count: int
    listed_capacity_kw: float
    next_event_count_24h: int = 0
    last_event_perf_pct: Optional[float] = None


class AdminZoneDetail(AdminZoneSummary):
    devices: list["DominionDeviceResponse"] = []


class AdminEventSummary(BaseModel):
    event_id: str
    device_id_external: str
    primary_pnode_id: str
    primary_pnode_name: Optional[str] = None
    zone_id: Optional[str] = None
    operating_date: date
    start_utc: datetime
    end_utc: datetime
    duration_hours: int
    stressed_hours: int
    extreme_hours: int
    has_mandatory: bool
    listed_capacity_kw_avg: Optional[float] = None
    realized_capacity_kw_avg: Optional[float] = None
    performance_pct: Optional[float] = None
    mandatory_performance_pct: Optional[float] = None


class AdminEventListResponse(BaseModel):
    window_start: Optional[date] = None
    window_end: Optional[date] = None
    total: int
    events: list[AdminEventSummary]


class AdminEventHour(BaseModel):
    hour_index: int
    interval_start_utc: datetime
    period_tier: Optional[str]
    dispatch_signal_program: float
    listed_kw_ask: Optional[float] = None
    realized_kw: Optional[float] = None


class AdminEventDetail(AdminEventSummary):
    hours: list[AdminEventHour] = []


class AdminDashboardZoneSlice(BaseModel):
    zone_id: str
    events: int
    peak_kw: float


class AdminDashboardHour(BaseModel):
    hour_utc: datetime
    program_signal: float


class AdminDashboardToday(BaseModel):
    operating_date: date
    forecast_basis: str  # "tomorrow_da" | "most_recent_da"
    ingestion_run_id: Optional[int] = None
    events_forecast: int
    peak_program_kw: float
    peak_window_ept: Optional[list[str]] = None
    by_zone: list[AdminDashboardZoneSlice]
    fleet_24h_signal: list[AdminDashboardHour]


class AdminDeviceRecentEvent(AdminEventSummary):
    pass


class AdminDeviceSummary(BaseModel):
    device_id_external: str
    primary_pnode_id: str
    primary_pnode_name: Optional[str] = None
    zone_id: Optional[str] = None
    listed_capacity_kw: Optional[float] = None
    asset_lat: Optional[float] = None
    asset_lon: Optional[float] = None
    window_start: Optional[date] = None
    window_end: Optional[date] = None
    event_count: int
    total_dispatch_hours: int
    avg_performance_pct: Optional[float] = None
    mandatory_performance_pct: Optional[float] = None
    total_realized_energy_mwh: float
    rank_in_fleet: Optional[int] = None
    recent_events: list[AdminDeviceRecentEvent] = []


AdminZoneDetail.model_rebuild()


# ───────────────────────── admin / exec heatmap ─────────────────────────


class AdminCongestionHeatmapPoint(BaseModel):
    pnode_id: str
    pnode_name: Optional[str] = None
    lat: float
    lon: float
    max_abs_congestion: float
    mean_abs_congestion: float


class AdminCongestionHeatmapResponse(BaseModel):
    operating_date: date
    point_count: int
    points: list[AdminCongestionHeatmapPoint]
