"""Batch valuation API endpoints."""

from fastapi import APIRouter, Depends, Request
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.orm import Session

from app.auth import require_api_key
from app.database import get_db
from app.schemas.batch_schemas import (
    BatchValuationRequest,
    BatchValuationResponse,
    BatchItemResult,
)
from core.geo_resolver import resolve
from core.valuation_engine import compute_der_value

router = APIRouter(prefix="/api/v1")

limiter = Limiter(key_func=get_remote_address)


@router.post(
    "/valuations/batch",
    response_model=BatchValuationResponse,
    dependencies=[Depends(require_api_key)],
)
@limiter.limit("10/minute")
def batch_valuation(
    request: Request,
    body: BatchValuationRequest,
    db: Session = Depends(get_db),
):
    """Compute constraint-relief valuations for up to 100 DER placements.

    Requires X-API-Key header. Rate-limited to 10 requests per minute.
    """
    results: list[BatchItemResult] = []
    error_count = 0

    for item in body.items:
        try:
            resolution = resolve(db, item.lat, item.lon)

            if not resolution.iso_id:
                results.append(
                    BatchItemResult(
                        label=item.label,
                        lat=item.lat,
                        lon=item.lon,
                        der_type=item.der_type,
                        capacity_mw=item.capacity_mw,
                        error=f"Could not resolve ({item.lat}, {item.lon}) to any ISO/zone",
                    )
                )
                error_count += 1
                continue

            val = compute_der_value(
                db=db,
                resolution=resolution,
                der_type=item.der_type,
                capacity_mw=item.capacity_mw,
                pipeline_run_id=body.pipeline_run_id,
            )

            results.append(
                BatchItemResult(
                    label=item.label,
                    lat=item.lat,
                    lon=item.lon,
                    der_type=item.der_type,
                    capacity_mw=item.capacity_mw,
                    iso_code=resolution.iso_code,
                    zone_code=resolution.zone_code,
                    total_constraint_relief_value=val.total_constraint_relief_value,
                    value_per_kw_year=val.value_per_kw_year,
                    value_tier=val.value_tier,
                )
            )
        except Exception as e:
            results.append(
                BatchItemResult(
                    label=item.label,
                    lat=item.lat,
                    lon=item.lon,
                    der_type=item.der_type,
                    capacity_mw=item.capacity_mw,
                    error=str(e),
                )
            )
            error_count += 1

    return BatchValuationResponse(
        count=len(results),
        results=results,
        errors=error_count,
    )
