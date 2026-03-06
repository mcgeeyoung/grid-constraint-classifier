"""Pydantic schemas for DER profiles and intersection responses."""

from typing import Optional
from pydantic import BaseModel

from app.schemas.constraint_schemas import ConstraintProfileResponse


class DERProfileResponse(BaseModel):
    id: int
    der_type: str
    eac_category: str
    profile_12x24: Optional[dict] = None
    is_dispatchable: bool
    max_dispatch_hours: Optional[float] = None
    dispatch_power_mw: Optional[float] = None
    capacity_factor: Optional[float] = None

    class Config:
        from_attributes = True


class IntersectionResponse(BaseModel):
    constraint_profile: ConstraintProfileResponse
    der_profile: DERProfileResponse
    coincidence_factor: float
    overlap_hours: int
    overlap_12x24: Optional[dict] = None
    value_per_kw_year: float
    value_tier: str


class LoadshapeHourResponse(BaseModel):
    hour: int
    avg_congestion: float


class GridLevelScore(BaseModel):
    level: str  # "substation", "pnode", "zone", "utility", "ba"
    name: Optional[str] = None
    constraint_loadshape: Optional[dict] = None  # 12x24
    grid_score: Optional[float] = None  # 0-1 normalized
    score_label: str = ""  # "Loading", "Congestion Severity", etc.
    tier: Optional[str] = None  # CRITICAL/ELEVATED/MODERATE/LOW
    coincidence_factor: Optional[float] = None  # 0-1 cosine similarity
    overlap_12x24: Optional[dict] = None  # elementwise product


class DERGridScoresResponse(BaseModel):
    location: dict  # {lat, lon, iso_code, zone_code, substation_name, ba_code}
    der_type: str
    der_profile_12x24: Optional[dict] = None
    levels: list[GridLevelScore] = []
