"""Pydantic schemas for valuation and geo-resolution endpoints."""

from typing import Optional

from pydantic import BaseModel, Field


# --- Request schemas ---

class ProspectiveValuationRequest(BaseModel):
    lat: float = Field(..., description="Latitude of the DER location")
    lon: float = Field(..., description="Longitude of the DER location")
    der_type: str = Field(..., description="DER type (solar, storage, demand_response, etc.)")
    capacity_mw: float = Field(..., gt=0, description="DER nameplate capacity in MW")
    pipeline_run_id: Optional[int] = Field(None, description="Specific pipeline run (defaults to latest)")


class CreateDERLocationRequest(BaseModel):
    lat: float
    lon: float
    der_type: str
    capacity_mw: float = Field(..., gt=0)
    source: str = Field("manual", description="Source: hypothetical, wattcarbon, manual")
    wattcarbon_asset_id: Optional[str] = None


# --- Response schemas ---

class GeoResolutionResponse(BaseModel):
    lat: float
    lon: float
    iso_code: Optional[str] = None
    zone_code: Optional[str] = None
    substation_name: Optional[str] = None
    substation_distance_km: Optional[float] = None
    nearest_pnode_name: Optional[str] = None
    pnode_distance_km: Optional[float] = None
    feeder_id: Optional[int] = None
    circuit_id: Optional[int] = None
    resolution_depth: str
    confidence: str
    errors: list[str] = []


class ValuationResponse(BaseModel):
    zone_congestion_value: float
    pnode_multiplier: float
    substation_loading_value: float
    feeder_capacity_value: float
    total_constraint_relief_value: float
    coincidence_factor: float
    effective_capacity_mw: float
    value_per_kw_year: float
    value_tier: str
    value_breakdown: dict
    geo_resolution: GeoResolutionResponse


class DERLocationResponse(BaseModel):
    id: int
    iso_code: Optional[str] = None
    zone_code: Optional[str] = None
    substation_name: Optional[str] = None
    der_type: str
    eac_category: Optional[str] = None
    capacity_mw: float
    lat: Optional[float] = None
    lon: Optional[float] = None
    source: str
    wattcarbon_asset_id: Optional[str] = None
    resolution_depth: Optional[str] = None

    class Config:
        from_attributes = True
