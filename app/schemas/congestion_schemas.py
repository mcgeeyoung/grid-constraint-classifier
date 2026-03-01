"""Pydantic schemas for congestion pipeline endpoints."""

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel


class BAResponse(BaseModel):
    ba_code: str
    ba_name: Optional[str] = None
    region: Optional[str] = None
    interconnection: Optional[str] = None
    is_rto: bool = False
    rto_neighbor: Optional[str] = None
    rto_neighbor_secondary: Optional[str] = None
    interface_points: Optional[list] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    transfer_limit_mw: Optional[float] = None
    transfer_limit_method: Optional[str] = None

    class Config:
        from_attributes = True


class CongestionScoreResponse(BaseModel):
    ba_code: str
    ba_name: Optional[str] = None
    region: Optional[str] = None
    period_start: date
    period_end: date
    period_type: Optional[str] = None
    hours_total: Optional[int] = None
    hours_importing: Optional[int] = None
    pct_hours_importing: Optional[float] = None
    hours_above_80: Optional[int] = None
    hours_above_90: Optional[int] = None
    hours_above_95: Optional[int] = None
    avg_import_pct_of_load: Optional[float] = None
    max_import_pct_of_load: Optional[float] = None
    avg_congestion_premium: Optional[float] = None
    congestion_opportunity_score: Optional[float] = None
    transfer_limit_used: Optional[float] = None
    lmp_coverage: Optional[str] = None
    data_quality_flag: Optional[str] = None

    class Config:
        from_attributes = True


class DurationCurveResponse(BaseModel):
    ba_code: str
    ba_name: Optional[str] = None
    year: int
    transfer_limit_mw: Optional[float] = None
    values: list[float]
    hours_count: int


class HourlyDataResponse(BaseModel):
    timestamp_utc: datetime
    demand_mw: Optional[float] = None
    net_generation_mw: Optional[float] = None
    total_interchange_mw: Optional[float] = None
    net_imports_mw: Optional[float] = None
    import_utilization: Optional[float] = None

    class Config:
        from_attributes = True
