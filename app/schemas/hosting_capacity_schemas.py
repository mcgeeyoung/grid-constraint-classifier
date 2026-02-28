"""Pydantic schemas for hosting capacity endpoints."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class UtilityResponse(BaseModel):
    utility_code: str
    utility_name: str
    parent_company: Optional[str] = None
    iso_code: Optional[str] = None
    states: Optional[list] = None
    data_source_type: str
    last_ingested_at: Optional[datetime] = None
    total_feeders: Optional[int] = None
    total_hosting_capacity_mw: Optional[float] = None
    total_remaining_capacity_mw: Optional[float] = None

    class Config:
        from_attributes = True


class HostingCapacityResponse(BaseModel):
    id: int
    utility_code: str
    feeder_id_external: str
    feeder_name: Optional[str] = None
    substation_name: Optional[str] = None
    hosting_capacity_mw: Optional[float] = None
    hosting_capacity_min_mw: Optional[float] = None
    hosting_capacity_max_mw: Optional[float] = None
    remaining_capacity_mw: Optional[float] = None
    installed_dg_mw: Optional[float] = None
    queued_dg_mw: Optional[float] = None
    constraining_metric: Optional[str] = None
    voltage_kv: Optional[float] = None
    phase_config: Optional[str] = None
    centroid_lat: Optional[float] = None
    centroid_lon: Optional[float] = None

    class Config:
        from_attributes = True


class HCSummaryResponse(BaseModel):
    utility_code: str
    utility_name: str
    total_feeders: int
    total_hosting_capacity_mw: float
    total_installed_dg_mw: float
    total_remaining_capacity_mw: float
    avg_utilization_pct: Optional[float] = None
    constrained_feeders_count: int
    constraint_breakdown: Optional[dict] = None
    computed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class HCIngestionRunResponse(BaseModel):
    id: int
    utility_code: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    status: str
    records_fetched: Optional[int] = None
    records_written: Optional[int] = None
    error_message: Optional[str] = None

    class Config:
        from_attributes = True


class HCNearbyResponse(BaseModel):
    id: int
    utility_code: str
    feeder_id_external: str
    feeder_name: Optional[str] = None
    hosting_capacity_mw: Optional[float] = None
    remaining_capacity_mw: Optional[float] = None
    constraining_metric: Optional[str] = None
    centroid_lat: Optional[float] = None
    centroid_lon: Optional[float] = None
    distance_km: float

    class Config:
        from_attributes = True
