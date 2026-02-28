"""Pydantic schemas for GeoPackage infrastructure endpoints."""

from typing import Optional

from pydantic import BaseModel


class GPKGPowerLineResponse(BaseModel):
    id: int
    osm_id: Optional[int] = None
    name: Optional[str] = None
    operator: Optional[str] = None
    max_voltage_kv: Optional[float] = None
    voltages: Optional[str] = None
    circuits: Optional[int] = None
    location: Optional[str] = None

    class Config:
        from_attributes = True


class GPKGSubstationResponse(BaseModel):
    id: int
    osm_id: Optional[int] = None
    name: Optional[str] = None
    operator: Optional[str] = None
    substation_type: Optional[str] = None
    max_voltage_kv: Optional[float] = None
    voltages: Optional[str] = None
    centroid_lat: Optional[float] = None
    centroid_lon: Optional[float] = None

    class Config:
        from_attributes = True


class GPKGPowerPlantResponse(BaseModel):
    id: int
    osm_id: Optional[int] = None
    name: Optional[str] = None
    operator: Optional[str] = None
    source: Optional[str] = None
    method: Optional[str] = None
    output_mw: Optional[float] = None
    centroid_lat: Optional[float] = None
    centroid_lon: Optional[float] = None

    class Config:
        from_attributes = True


class GPKGLayerSummary(BaseModel):
    layer: str
    total_features: int
    with_name: int
    with_operator: int

    class Config:
        from_attributes = True
