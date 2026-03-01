"""API v1 routes for GeoPackage infrastructure data (power lines, substations, plants)."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.cache import cache_response

from app.api.v1.spatial import BBox, parse_bbox
from app.database import get_db
from app.models.gpkg import GPKGPowerLine, GPKGSubstation, GPKGPowerPlant
from app.schemas.gpkg_schemas import (
    GPKGPowerLineResponse,
    GPKGSubstationResponse,
    GPKGPowerPlantResponse,
    GPKGLayerSummary,
)

router = APIRouter(prefix="/api/v1/infrastructure", tags=["infrastructure"])


# ------------------------------------------------------------------
# Summary
# ------------------------------------------------------------------

@router.get("/summary", response_model=list[GPKGLayerSummary])
@cache_response("infra-summary", ttl=3600)
def infrastructure_summary(request: Request = None, db: Session = Depends(get_db)):
    """Get feature counts for all GeoPackage infrastructure layers."""
    results = []
    for model, layer_name in [
        (GPKGPowerLine, "power_lines"),
        (GPKGSubstation, "substations"),
        (GPKGPowerPlant, "power_plants"),
    ]:
        row = db.query(
            func.count(model.id),
            func.count(model.name),
            func.count(model.operator),
        ).first()
        results.append(GPKGLayerSummary(
            layer=layer_name,
            total_features=row[0],
            with_name=row[1],
            with_operator=row[2],
        ))
    return results


# ------------------------------------------------------------------
# Power Lines
# ------------------------------------------------------------------

@router.get("/power-lines", response_model=list[GPKGPowerLineResponse])
@cache_response("infra-lines", ttl=300)
def list_power_lines(
    limit: int = Query(default=200, le=5000),
    offset: int = Query(default=0, ge=0),
    bbox: Optional[BBox] = Depends(parse_bbox),
    min_voltage_kv: Optional[float] = Query(
        None, description="Minimum voltage in kV",
    ),
    operator: Optional[str] = Query(
        None, description="Filter by operator (case-insensitive contains)",
    ),
    request: Request = None,
    db: Session = Depends(get_db),
):
    """List power lines with optional spatial and attribute filters.

    Supports bbox filtering: ?bbox=west,south,east,north
    """
    query = db.query(GPKGPowerLine)

    if bbox:
        query = query.filter(bbox.filter_column(GPKGPowerLine.geom))

    if min_voltage_kv is not None:
        query = query.filter(GPKGPowerLine.max_voltage_kv >= min_voltage_kv)

    if operator:
        query = query.filter(GPKGPowerLine.operator.ilike(f"%{operator}%"))

    records = query.offset(offset).limit(limit).all()
    return [
        GPKGPowerLineResponse(
            id=r.id,
            osm_id=r.osm_id,
            name=r.name,
            operator=r.operator,
            max_voltage_kv=r.max_voltage_kv,
            voltages=r.voltages,
            circuits=r.circuits,
            location=r.location,
        )
        for r in records
    ]


@router.get("/power-lines/geojson")
def power_lines_geojson(
    limit: int = Query(default=5000, le=50000),
    bbox: Optional[BBox] = Depends(parse_bbox),
    min_voltage_kv: Optional[float] = Query(None),
    db: Session = Depends(get_db),
):
    """Export power lines as GeoJSON FeatureCollection.

    Supports bbox filtering: ?bbox=west,south,east,north
    Note: Returns simplified centroid points for large result sets.
    For full line geometry, use the MVT tile endpoint.
    """
    from geoalchemy2.functions import ST_AsGeoJSON

    query = db.query(
        GPKGPowerLine.id,
        GPKGPowerLine.name,
        GPKGPowerLine.operator,
        GPKGPowerLine.max_voltage_kv,
        GPKGPowerLine.circuits,
        GPKGPowerLine.location,
        ST_AsGeoJSON(GPKGPowerLine.geom).label("geojson"),
    ).filter(GPKGPowerLine.geom.isnot(None))

    if bbox:
        query = query.filter(bbox.filter_column(GPKGPowerLine.geom))

    if min_voltage_kv is not None:
        query = query.filter(GPKGPowerLine.max_voltage_kv >= min_voltage_kv)

    rows = query.limit(limit).all()

    import json
    features = []
    for r in rows:
        features.append({
            "type": "Feature",
            "geometry": json.loads(r.geojson),
            "properties": {
                "id": r.id,
                "name": r.name,
                "operator": r.operator,
                "max_voltage_kv": r.max_voltage_kv,
                "circuits": r.circuits,
                "location": r.location,
            },
        })

    return {"type": "FeatureCollection", "features": features}


@router.get("/power-lines/voltage-stats")
@cache_response("infra-voltage-stats", ttl=3600)
def power_lines_voltage_stats(
    bbox: Optional[BBox] = Depends(parse_bbox),
    request: Request = None,
    db: Session = Depends(get_db),
):
    """Get voltage distribution statistics for power lines."""
    query = db.query(
        GPKGPowerLine.max_voltage_kv,
        func.count(GPKGPowerLine.id),
    ).filter(GPKGPowerLine.max_voltage_kv.isnot(None))

    if bbox:
        query = query.filter(bbox.filter_column(GPKGPowerLine.geom))

    rows = (
        query.group_by(GPKGPowerLine.max_voltage_kv)
        .order_by(func.count(GPKGPowerLine.id).desc())
        .limit(20)
        .all()
    )

    return {
        "voltage_distribution": [
            {"voltage_kv": r[0], "count": r[1]} for r in rows
        ],
    }


# ------------------------------------------------------------------
# Substations
# ------------------------------------------------------------------

@router.get("/substations", response_model=list[GPKGSubstationResponse])
@cache_response("infra-substations", ttl=300)
def list_substations(
    limit: int = Query(default=200, le=5000),
    offset: int = Query(default=0, ge=0),
    bbox: Optional[BBox] = Depends(parse_bbox),
    substation_type: Optional[str] = Query(
        None, description="Filter by substation type (e.g. transmission, distribution)",
    ),
    operator: Optional[str] = Query(
        None, description="Filter by operator (case-insensitive contains)",
    ),
    min_voltage_kv: Optional[float] = Query(None),
    request: Request = None,
    db: Session = Depends(get_db),
):
    """List substations with optional spatial and attribute filters.

    Supports bbox filtering: ?bbox=west,south,east,north
    """
    query = db.query(GPKGSubstation)

    if bbox:
        query = query.filter(bbox.filter_column(GPKGSubstation.geom))

    if substation_type:
        query = query.filter(GPKGSubstation.substation_type == substation_type)

    if operator:
        query = query.filter(GPKGSubstation.operator.ilike(f"%{operator}%"))

    if min_voltage_kv is not None:
        query = query.filter(GPKGSubstation.max_voltage_kv >= min_voltage_kv)

    records = query.offset(offset).limit(limit).all()
    return [
        GPKGSubstationResponse(
            id=r.id,
            osm_id=r.osm_id,
            name=r.name,
            operator=r.operator,
            substation_type=r.substation_type,
            max_voltage_kv=r.max_voltage_kv,
            voltages=r.voltages,
            centroid_lat=r.centroid_lat,
            centroid_lon=r.centroid_lon,
        )
        for r in records
    ]


@router.get("/substations/geojson")
def substations_geojson(
    limit: int = Query(default=5000, le=50000),
    bbox: Optional[BBox] = Depends(parse_bbox),
    substation_type: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """Export substations as GeoJSON FeatureCollection.

    Supports bbox filtering: ?bbox=west,south,east,north
    """
    from geoalchemy2.functions import ST_AsGeoJSON

    query = db.query(
        GPKGSubstation.id,
        GPKGSubstation.name,
        GPKGSubstation.operator,
        GPKGSubstation.substation_type,
        GPKGSubstation.max_voltage_kv,
        ST_AsGeoJSON(GPKGSubstation.geom).label("geojson"),
    ).filter(GPKGSubstation.geom.isnot(None))

    if bbox:
        query = query.filter(bbox.filter_column(GPKGSubstation.geom))

    if substation_type:
        query = query.filter(GPKGSubstation.substation_type == substation_type)

    rows = query.limit(limit).all()

    import json
    features = []
    for r in rows:
        features.append({
            "type": "Feature",
            "geometry": json.loads(r.geojson),
            "properties": {
                "id": r.id,
                "name": r.name,
                "operator": r.operator,
                "substation_type": r.substation_type,
                "max_voltage_kv": r.max_voltage_kv,
            },
        })

    return {"type": "FeatureCollection", "features": features}


@router.get("/substations/type-stats")
@cache_response("infra-type-stats", ttl=3600)
def substations_type_stats(
    bbox: Optional[BBox] = Depends(parse_bbox),
    request: Request = None,
    db: Session = Depends(get_db),
):
    """Get substation type distribution statistics."""
    query = db.query(
        GPKGSubstation.substation_type,
        func.count(GPKGSubstation.id),
    )

    if bbox:
        query = query.filter(bbox.filter_column(GPKGSubstation.geom))

    rows = (
        query.group_by(GPKGSubstation.substation_type)
        .order_by(func.count(GPKGSubstation.id).desc())
        .all()
    )

    return {
        "type_distribution": [
            {"type": r[0] or "unknown", "count": r[1]} for r in rows
        ],
    }


# ------------------------------------------------------------------
# Power Plants
# ------------------------------------------------------------------

@router.get("/power-plants", response_model=list[GPKGPowerPlantResponse])
@cache_response("infra-plants", ttl=300)
def list_power_plants(
    limit: int = Query(default=200, le=5000),
    offset: int = Query(default=0, ge=0),
    bbox: Optional[BBox] = Depends(parse_bbox),
    source: Optional[str] = Query(
        None, description="Filter by energy source (e.g. solar, wind, gas)",
    ),
    operator: Optional[str] = Query(
        None, description="Filter by operator (case-insensitive contains)",
    ),
    min_output_mw: Optional[float] = Query(None),
    request: Request = None,
    db: Session = Depends(get_db),
):
    """List power plants with optional spatial and attribute filters.

    Supports bbox filtering: ?bbox=west,south,east,north
    """
    query = db.query(GPKGPowerPlant)

    if bbox:
        query = query.filter(bbox.filter_column(GPKGPowerPlant.geom))

    if source:
        query = query.filter(GPKGPowerPlant.source == source)

    if operator:
        query = query.filter(GPKGPowerPlant.operator.ilike(f"%{operator}%"))

    if min_output_mw is not None:
        query = query.filter(GPKGPowerPlant.output_mw >= min_output_mw)

    records = query.offset(offset).limit(limit).all()
    return [
        GPKGPowerPlantResponse(
            id=r.id,
            osm_id=r.osm_id,
            name=r.name,
            operator=r.operator,
            source=r.source,
            method=r.method,
            output_mw=r.output_mw,
            centroid_lat=r.centroid_lat,
            centroid_lon=r.centroid_lon,
        )
        for r in records
    ]


@router.get("/power-plants/geojson")
def power_plants_geojson(
    limit: int = Query(default=5000, le=50000),
    bbox: Optional[BBox] = Depends(parse_bbox),
    source: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """Export power plants as GeoJSON FeatureCollection.

    Supports bbox filtering: ?bbox=west,south,east,north
    """
    from geoalchemy2.functions import ST_AsGeoJSON

    query = db.query(
        GPKGPowerPlant.id,
        GPKGPowerPlant.name,
        GPKGPowerPlant.operator,
        GPKGPowerPlant.source,
        GPKGPowerPlant.method,
        GPKGPowerPlant.output_mw,
        ST_AsGeoJSON(GPKGPowerPlant.geom).label("geojson"),
    ).filter(GPKGPowerPlant.geom.isnot(None))

    if bbox:
        query = query.filter(bbox.filter_column(GPKGPowerPlant.geom))

    if source:
        query = query.filter(GPKGPowerPlant.source == source)

    rows = query.limit(limit).all()

    import json
    features = []
    for r in rows:
        features.append({
            "type": "Feature",
            "geometry": json.loads(r.geojson),
            "properties": {
                "id": r.id,
                "name": r.name,
                "operator": r.operator,
                "source": r.source,
                "method": r.method,
                "output_mw": r.output_mw,
            },
        })

    return {"type": "FeatureCollection", "features": features}


@router.get("/power-plants/source-stats")
@cache_response("infra-source-stats", ttl=3600)
def power_plants_source_stats(
    bbox: Optional[BBox] = Depends(parse_bbox),
    request: Request = None,
    db: Session = Depends(get_db),
):
    """Get power plant source/fuel distribution with total capacity."""
    query = db.query(
        GPKGPowerPlant.source,
        func.count(GPKGPowerPlant.id),
        func.sum(GPKGPowerPlant.output_mw),
    )

    if bbox:
        query = query.filter(bbox.filter_column(GPKGPowerPlant.geom))

    rows = (
        query.group_by(GPKGPowerPlant.source)
        .order_by(func.count(GPKGPowerPlant.id).desc())
        .all()
    )

    return {
        "source_distribution": [
            {
                "source": r[0] or "unknown",
                "count": r[1],
                "total_output_mw": round(r[2], 1) if r[2] else None,
            }
            for r in rows
        ],
    }
