"""Pydantic schemas for constraint profiles, annotations, and geo resolution."""

from typing import Optional
from pydantic import BaseModel


class AnnotationResponse(BaseModel):
    id: int
    annotation_type: str
    title: str
    summary: Optional[str] = None
    planned_solution: Optional[str] = None
    deferral_value_estimate: Optional[float] = None
    source_url: Optional[str] = None
    confidence: float

    class Config:
        from_attributes = True


class ConstraintProfileResponse(BaseModel):
    id: int
    location_level: str
    location_id: int
    location_name: Optional[str] = None
    constraint_type: str
    period_year: int
    profile_12x24: dict
    peak_intensity: float
    peak_month: int
    peak_hour: int
    mean_intensity: float
    total_constrained_hours: int
    constrained_hours_pct: float
    severity_score: float
    severity_tier: str
    avg_marginal_cost: Optional[float] = None
    annual_cost: Optional[float] = None
    annotations: list[AnnotationResponse] = []

    class Config:
        from_attributes = True


class ZoneConstraintSummaryResponse(BaseModel):
    iso_code: str
    zone_code: str
    zone_name: str
    centroid_lat: Optional[float] = None
    centroid_lon: Optional[float] = None
    primary_constraint_type: Optional[str] = None
    severity_score: Optional[float] = None
    severity_tier: Optional[str] = None
    peak_month: Optional[int] = None
    peak_hour: Optional[int] = None
    constrained_hours_pct: Optional[float] = None
    best_der_type: Optional[str] = None
    best_der_value_per_kw_year: Optional[float] = None
    annotation_count: int = 0


class GeoResolutionResponse(BaseModel):
    lat: float
    lon: float
    iso_code: Optional[str] = None
    zone_code: Optional[str] = None
    substation_name: Optional[str] = None
    nearest_pnode_name: Optional[str] = None
    feeder_id: Optional[str] = None
    resolution_depth: str
    constraints: list[ConstraintProfileResponse] = []
    best_der: Optional[str] = None
    total_value_per_kw_year: Optional[float] = None
