"""Pydantic schemas for the refocused valuation endpoints."""

from typing import Optional
from pydantic import BaseModel, Field

from app.schemas.constraint_schemas import (
    GeoResolutionResponse,
    AnnotationResponse,
)


class ProspectiveValuationRequest(BaseModel):
    lat: float = Field(..., description="Latitude of the DER location")
    lon: float = Field(..., description="Longitude of the DER location")
    der_type: str = Field(..., description="DER type (solar, storage, etc.)")
    capacity_mw: float = Field(1.0, gt=0, description="DER nameplate capacity in MW")


class ValueStackResponse(BaseModel):
    geo_resolution: GeoResolutionResponse
    congestion_value_per_kw_year: float
    loading_value_per_kw_year: float
    capacity_value_per_kw_year: float
    import_stress_value_per_kw_year: float
    total_value_per_kw_year: float
    composite_coincidence_factor: float
    value_tier: str
    constraint_layers: list[dict]
    annotations: list[AnnotationResponse] = []


class DERComparisonItem(BaseModel):
    der_type: str
    eac_category: str
    total_value_per_kw_year: float
    coincidence_factor: float
    value_tier: str
    is_dispatchable: bool


class DERComparisonResponse(BaseModel):
    geo_resolution: GeoResolutionResponse
    comparisons: list[DERComparisonItem]


class LocationRankingResponse(BaseModel):
    location_level: str
    location_id: int
    location_name: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    total_value_per_kw_year: float
    value_tier: str
    coincidence_factor: float


class BatchValuationRequest(BaseModel):
    items: list[ProspectiveValuationRequest] = Field(
        ..., max_length=100, description="Up to 100 valuation requests")
