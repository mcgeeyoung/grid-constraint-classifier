"""Pydantic schemas for hierarchy browsing endpoints."""

from typing import Optional

from pydantic import BaseModel, Field


class SubstationResponse(BaseModel):
    id: int
    substation_name: str
    bank_name: Optional[str] = None
    division: Optional[str] = None
    facility_rating_mw: Optional[float] = None
    facility_loading_mw: Optional[float] = None
    peak_loading_pct: Optional[float] = None
    facility_type: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    zone_code: Optional[str] = None
    nearest_pnode_name: Optional[str] = None

    class Config:
        from_attributes = True


class SubstationDetailResponse(SubstationResponse):
    zone_id: Optional[int] = None
    nearest_pnode_id: Optional[int] = None
    feeder_count: int = 0


class FeederResponse(BaseModel):
    id: int
    substation_id: int
    feeder_id_external: Optional[str] = None
    capacity_mw: Optional[float] = None
    peak_loading_mw: Optional[float] = None
    peak_loading_pct: Optional[float] = None
    voltage_kv: Optional[float] = None

    class Config:
        from_attributes = True


class HierarchyScoreResponse(BaseModel):
    id: int
    pipeline_run_id: int
    level: str
    entity_id: int
    congestion_score: Optional[float] = None
    loading_score: Optional[float] = None
    combined_score: Optional[float] = None
    constraint_tier: Optional[str] = None
    entity_name: Optional[str] = Field(None, description="Zone code or substation name")

    class Config:
        from_attributes = True
