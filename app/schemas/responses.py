"""Pydantic response models for the API."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class ISOResponse(BaseModel):
    iso_code: str
    iso_name: str
    timezone: str
    has_decomposition: bool
    has_node_pricing: bool

    class Config:
        from_attributes = True


class ZoneResponse(BaseModel):
    zone_code: str
    zone_name: Optional[str] = None
    centroid_lat: Optional[float] = None
    centroid_lon: Optional[float] = None
    states: Optional[list] = None
    boundary_geojson: Optional[dict] = None

    class Config:
        from_attributes = True


class ZoneClassificationResponse(BaseModel):
    zone_code: str
    zone_name: Optional[str] = None
    classification: str
    transmission_score: float
    generation_score: float
    avg_abs_congestion: Optional[float] = None
    max_congestion: Optional[float] = None
    congested_hours_pct: Optional[float] = None


class PnodeScoreResponse(BaseModel):
    node_id_external: str
    node_name: Optional[str] = None
    severity_score: float
    tier: str
    avg_congestion: Optional[float] = None
    max_congestion: Optional[float] = None
    congested_hours_pct: Optional[float] = None
    lat: Optional[float] = None
    lon: Optional[float] = None


class ZoneLMPResponse(BaseModel):
    timestamp_utc: datetime
    lmp: float
    energy: Optional[float] = None
    congestion: Optional[float] = None
    loss: Optional[float] = None
    hour_local: int
    month: int


class LoadshapeHourResponse(BaseModel):
    hour: int
    avg_congestion: float


class SubstationLoadshapeHourResponse(BaseModel):
    hour: int
    load_low_kw: float
    load_high_kw: float


class DataCenterResponse(BaseModel):
    external_slug: Optional[str] = None
    facility_name: Optional[str] = None
    status: Optional[str] = None
    capacity_mw: Optional[float] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    state_code: Optional[str] = None
    county: Optional[str] = None
    operator: Optional[str] = None
    iso_code: Optional[str] = None
    zone_code: Optional[str] = None


class DERRecommendationResponse(BaseModel):
    zone_code: str
    classification: Optional[str] = None
    rationale: Optional[str] = None
    congestion_value: Optional[float] = None
    primary_rec: Optional[dict] = None
    secondary_rec: Optional[dict] = None
    tertiary_rec: Optional[dict] = None


class PipelineRunResponse(BaseModel):
    id: int
    iso_code: str
    year: int
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    status: str
    zone_lmp_rows: Optional[int] = None
    error_message: Optional[str] = None


class OverviewResponse(BaseModel):
    iso_code: str
    iso_name: str
    zones_count: int
    latest_run_year: Optional[int] = None
    latest_run_status: Optional[str] = None
    transmission_constrained: int = 0
    generation_constrained: int = 0
    both_constrained: int = 0
    unconstrained: int = 0


class TopZone(BaseModel):
    zone_code: str
    zone_name: Optional[str] = None
    avg_constraint_value: float


class ValueSummaryResponse(BaseModel):
    iso_code: str
    iso_name: str
    total_zones: int
    constrained_zones: int
    total_substations: int
    overloaded_substations: int
    total_der_locations: int
    total_portfolio_value: float
    avg_value_per_kw_year: float
    tier_distribution: dict[str, int]
    top_zones: list[TopZone]
