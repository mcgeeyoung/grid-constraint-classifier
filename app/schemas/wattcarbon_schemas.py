"""Pydantic schemas for WattCarbon integration endpoints."""

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field


# --- Request schemas ---

class RetrospectiveValuationRequest(BaseModel):
    start: date = Field(..., description="Retrospective period start date")
    end: date = Field(..., description="Retrospective period end date")
    pipeline_run_id: Optional[int] = Field(None, description="Specific pipeline run (defaults to latest)")


# --- Response schemas ---

class WattCarbonAssetResponse(BaseModel):
    id: int
    wattcarbon_asset_id: Optional[str] = None
    iso_code: Optional[str] = None
    zone_code: Optional[str] = None
    substation_name: Optional[str] = None
    der_type: str
    eac_category: Optional[str] = None
    capacity_mw: float
    lat: Optional[float] = None
    lon: Optional[float] = None

    class Config:
        from_attributes = True


class WattCarbonAssetDetailResponse(WattCarbonAssetResponse):
    feeder_id: Optional[int] = None
    circuit_id: Optional[int] = None
    nearest_pnode_name: Optional[str] = None
    pnode_distance_km: Optional[float] = None
    latest_valuation: Optional[dict] = None
    latest_retrospective: Optional[dict] = None


class ProspectiveValuationResponse(BaseModel):
    wattcarbon_asset_id: str
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


class RetrospectiveValuationResponse(BaseModel):
    wattcarbon_asset_id: str
    actual_savings_mwh: float
    actual_constraint_relief_value: float
    actual_zone_congestion_value: float
    actual_substation_value: float
    actual_feeder_value: float
    retrospective_start: Optional[datetime] = None
    retrospective_end: Optional[datetime] = None
