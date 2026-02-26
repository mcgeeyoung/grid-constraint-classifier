"""Pydantic schemas for batch valuation endpoints."""

from typing import Optional

from pydantic import BaseModel, Field


class BatchItem(BaseModel):
    lat: float
    lon: float
    der_type: str
    capacity_mw: float = Field(gt=0)
    label: Optional[str] = None


class BatchValuationRequest(BaseModel):
    items: list[BatchItem] = Field(max_length=100)
    pipeline_run_id: Optional[int] = None


class BatchItemResult(BaseModel):
    label: Optional[str] = None
    lat: float
    lon: float
    der_type: str
    capacity_mw: float
    iso_code: Optional[str] = None
    zone_code: Optional[str] = None
    total_constraint_relief_value: Optional[float] = None
    value_per_kw_year: Optional[float] = None
    value_tier: Optional[str] = None
    error: Optional[str] = None


class BatchValuationResponse(BaseModel):
    count: int
    results: list[BatchItemResult]
    errors: int
