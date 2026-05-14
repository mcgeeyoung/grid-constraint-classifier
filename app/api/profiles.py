"""Profile routes: "Show me the temporal overlap."

Endpoints for viewing constraint profiles, DER output profiles,
and their intersection analysis.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.cache import cache_response
from app.database import get_db
from app.models.iso import ISO
from app.models.zone import Zone
from app.models.constraint_profile import ConstraintProfile
from app.models.constraint_annotation import ConstraintAnnotation
from app.models.constraint_der_intersection import ConstraintDERIntersection
from app.models.der_profile import DERProfile
from app.models.substation import Substation
from app.models.pnode_score import PnodeScore
from app.models.hierarchy_score import HierarchyScore
from app.models.congestion import CongestionScore
from app.models.substation_load_profile import SubstationLoadProfile
from app.models.pipeline_run import PipelineRun
from app.schemas.constraint_schemas import ConstraintProfileResponse, AnnotationResponse
from app.schemas.profile_schemas import (
    DERProfileResponse,
    IntersectionResponse,
    LoadshapeHourResponse,
    GridLevelScore,
    DERGridScoresResponse,
)

router = APIRouter(prefix="/api/profiles", tags=["profiles"])


@router.get("/constraint/{profile_id}")
def get_constraint_profile(
    profile_id: int,
    db: Session = Depends(get_db),
):
    """Full constraint profile detail."""
    cp = db.get(ConstraintProfile, profile_id)
    if not cp:
        raise HTTPException(status_code=404, detail="Constraint profile not found")

    annotations = db.query(ConstraintAnnotation).filter_by(
        constraint_profile_id=cp.id).all()

    return ConstraintProfileResponse(
        id=cp.id,
        location_level=cp.location_level,
        location_id=cp.location_id,
        constraint_type=cp.constraint_type,
        period_year=cp.period_year,
        profile_12x24=cp.profile_12x24,
        peak_intensity=cp.peak_intensity,
        peak_month=cp.peak_month,
        peak_hour=cp.peak_hour,
        mean_intensity=cp.mean_intensity,
        total_constrained_hours=cp.total_constrained_hours,
        constrained_hours_pct=cp.constrained_hours_pct,
        severity_score=cp.severity_score,
        severity_tier=cp.severity_tier,
        avg_marginal_cost=cp.avg_marginal_cost,
        annual_cost=cp.annual_cost,
        annotations=[AnnotationResponse.model_validate(a) for a in annotations],
    )


@router.get("/der/{der_type}")
def get_der_profile(
    der_type: str,
    db: Session = Depends(get_db),
):
    """Canonical DER output profile."""
    dp = (
        db.query(DERProfile)
        .filter_by(der_type=der_type, profile_source="canonical")
        .first()
    )
    if not dp:
        raise HTTPException(status_code=404, detail=f"DER profile for '{der_type}' not found")

    return DERProfileResponse(
        id=dp.id,
        der_type=dp.der_type,
        eac_category=dp.eac_category,
        profile_12x24=dp.profile_12x24,
        is_dispatchable=dp.is_dispatchable,
        max_dispatch_hours=dp.max_dispatch_hours,
        dispatch_power_mw=dp.dispatch_power_mw,
        capacity_factor=dp.capacity_factor,
    )


@router.get("/der")
def list_der_profiles(
    db: Session = Depends(get_db),
):
    """List all canonical DER profiles."""
    profiles = (
        db.query(DERProfile)
        .filter_by(profile_source="canonical")
        .order_by(DERProfile.der_type)
        .all()
    )
    return [
        DERProfileResponse(
            id=dp.id,
            der_type=dp.der_type,
            eac_category=dp.eac_category,
            profile_12x24=dp.profile_12x24,
            is_dispatchable=dp.is_dispatchable,
            max_dispatch_hours=dp.max_dispatch_hours,
            dispatch_power_mw=dp.dispatch_power_mw,
            capacity_factor=dp.capacity_factor,
        )
        for dp in profiles
    ]


@router.get("/intersection")
def get_intersection(
    constraint_profile_id: int = Query(...),
    der_type: str = Query(...),
    db: Session = Depends(get_db),
):
    """Intersection analysis between a constraint profile and DER type."""
    cp = db.get(ConstraintProfile, constraint_profile_id)
    if not cp:
        raise HTTPException(status_code=404, detail="Constraint profile not found")

    dp = (
        db.query(DERProfile)
        .filter_by(der_type=der_type, profile_source="canonical")
        .first()
    )
    if not dp:
        raise HTTPException(status_code=404, detail=f"DER profile for '{der_type}' not found")

    intersection = (
        db.query(ConstraintDERIntersection)
        .filter_by(constraint_profile_id=cp.id, der_profile_id=dp.id)
        .first()
    )

    if not intersection:
        # Compute on-the-fly
        from core.profile_utils import (
            flatten_12x24, cosine_similarity,
            elementwise_product_12x24, compute_overlap_hours,
        )

        if dp.is_dispatchable:
            cf = 1.0
            overlap = compute_overlap_hours(cp.profile_12x24, None)
            overlap_12x24 = None
        else:
            cp_vec = flatten_12x24(cp.profile_12x24)
            dp_vec = flatten_12x24(dp.profile_12x24)
            cf = cosine_similarity(cp_vec, dp_vec)
            overlap = compute_overlap_hours(cp.profile_12x24, dp.profile_12x24)
            overlap_12x24 = elementwise_product_12x24(cp.profile_12x24, dp.profile_12x24)

        base_cost = cp.avg_marginal_cost or 0.0
        val = base_cost * cf * cp.constrained_hours_pct
        from core.profile_utils import value_tier

        return {
            "constraint_profile": ConstraintProfileResponse(
                id=cp.id, location_level=cp.location_level,
                location_id=cp.location_id, constraint_type=cp.constraint_type,
                period_year=cp.period_year, profile_12x24=cp.profile_12x24,
                peak_intensity=cp.peak_intensity, peak_month=cp.peak_month,
                peak_hour=cp.peak_hour, mean_intensity=cp.mean_intensity,
                total_constrained_hours=cp.total_constrained_hours,
                constrained_hours_pct=cp.constrained_hours_pct,
                severity_score=cp.severity_score, severity_tier=cp.severity_tier,
                avg_marginal_cost=cp.avg_marginal_cost, annual_cost=cp.annual_cost,
            ),
            "der_profile": DERProfileResponse(
                id=dp.id, der_type=dp.der_type, eac_category=dp.eac_category,
                profile_12x24=dp.profile_12x24, is_dispatchable=dp.is_dispatchable,
                max_dispatch_hours=dp.max_dispatch_hours,
                dispatch_power_mw=dp.dispatch_power_mw,
                capacity_factor=dp.capacity_factor,
            ),
            "coincidence_factor": round(cf, 4),
            "overlap_hours": overlap,
            "overlap_12x24": overlap_12x24,
            "value_per_kw_year": round(val, 2),
            "value_tier": value_tier(val),
        }

    # Return pre-computed intersection
    annotations = db.query(ConstraintAnnotation).filter_by(
        constraint_profile_id=cp.id).all()

    return {
        "constraint_profile": ConstraintProfileResponse(
            id=cp.id, location_level=cp.location_level,
            location_id=cp.location_id, constraint_type=cp.constraint_type,
            period_year=cp.period_year, profile_12x24=cp.profile_12x24,
            peak_intensity=cp.peak_intensity, peak_month=cp.peak_month,
            peak_hour=cp.peak_hour, mean_intensity=cp.mean_intensity,
            total_constrained_hours=cp.total_constrained_hours,
            constrained_hours_pct=cp.constrained_hours_pct,
            severity_score=cp.severity_score, severity_tier=cp.severity_tier,
            avg_marginal_cost=cp.avg_marginal_cost, annual_cost=cp.annual_cost,
            annotations=[AnnotationResponse.model_validate(a) for a in annotations],
        ),
        "der_profile": DERProfileResponse(
            id=dp.id, der_type=dp.der_type, eac_category=dp.eac_category,
            profile_12x24=dp.profile_12x24, is_dispatchable=dp.is_dispatchable,
            max_dispatch_hours=dp.max_dispatch_hours,
            dispatch_power_mw=dp.dispatch_power_mw,
            capacity_factor=dp.capacity_factor,
        ),
        "coincidence_factor": intersection.coincidence_factor,
        "overlap_hours": intersection.overlap_hours,
        "overlap_12x24": intersection.overlap_12x24,
        "value_per_kw_year": intersection.value_per_kw_year,
        "value_tier": intersection.value_tier,
    }


@router.get("/zone/{iso_code}/{zone_code}/loadshape")
@cache_response("loadshape", ttl=300)
def zone_loadshape(
    iso_code: str,
    zone_code: str,
    month: Optional[int] = None,
    request: Request = None,
    db: Session = Depends(get_db),
):
    """Backward-compatible 24-hour congestion loadshape.

    Reads from constraint_profiles instead of old materialized view.
    """
    iso = db.query(ISO).filter(func.lower(ISO.iso_code) == iso_code.lower()).first()
    if not iso:
        raise HTTPException(status_code=404, detail=f"ISO '{iso_code}' not found")

    zone = db.query(Zone).filter_by(iso_id=iso.id, zone_code=zone_code).first()
    if not zone:
        raise HTTPException(status_code=404, detail=f"Zone '{zone_code}' not found")

    cp = (
        db.query(ConstraintProfile)
        .filter_by(
            location_level="zone",
            location_id=zone.id,
            constraint_type="congestion",
        )
        .order_by(ConstraintProfile.period_year.desc())
        .first()
    )

    if not cp or not cp.profile_12x24:
        return [LoadshapeHourResponse(hour=h, avg_congestion=0.0) for h in range(24)]

    if month and str(month) in cp.profile_12x24:
        hourly = cp.profile_12x24[str(month)]
    else:
        # Average across all months
        hourly = [0.0] * 24
        for m in range(1, 13):
            m_key = str(m)
            row = cp.profile_12x24.get(m_key, [0.0] * 24)
            for h in range(24):
                hourly[h] += row[h]
        hourly = [v / 12.0 for v in hourly]

    return [
        LoadshapeHourResponse(hour=h, avg_congestion=round(hourly[h], 4))
        for h in range(24)
    ]


@router.get("/der-grid-scores", response_model=DERGridScoresResponse)
def get_der_grid_scores(
    lat: float = Query(...),
    lon: float = Query(...),
    der_type: str = Query("solar"),
    iso_code: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """DER profile analysis at a location across all grid hierarchy levels.

    Resolves the grid hierarchy from lat/lon (substation, pnode, zone, utility, BA),
    then computes coincidence factors and overlap profiles between the selected
    DER type and constraint loadshapes at each level.
    """
    from core.der_profiles import get_der_profile, compute_coincidence_factor
    from core.profile_utils import elementwise_product_12x24

    # --- Resolve hierarchy from lat/lon ---
    # Find nearest substation
    deg_offset = 5.0 / 111.0  # 5 km search radius
    nearby_subs = (
        db.query(Substation)
        .filter(
            Substation.lat.isnot(None),
            Substation.lat.between(lat - deg_offset, lat + deg_offset),
            Substation.lon.between(lon - deg_offset, lon + deg_offset),
        )
        .all()
    )
    nearest_sub = min(
        nearby_subs,
        key=lambda s: (s.lat - lat) ** 2 + (s.lon - lon) ** 2,
    ) if nearby_subs else None

    # Resolve zone and ISO from substation (or directly from lat/lon)
    zone_obj = None
    iso_obj = None
    if nearest_sub:
        if nearest_sub.zone_id:
            zone_obj = db.get(Zone, nearest_sub.zone_id)
        if nearest_sub.iso_id:
            iso_obj = db.get(ISO, nearest_sub.iso_id)

    # If no substation found, use the iso_code hint from the frontend
    if not iso_obj and iso_code:
        iso_obj = db.query(ISO).filter(
            func.lower(ISO.iso_code) == iso_code.lower()
        ).first()

    # Last resort fallback
    if not iso_obj:
        iso_obj = db.query(ISO).filter(ISO.is_rto == True).first()

    # Get latest pipeline run for this ISO
    pipeline_run = None
    if iso_obj:
        pipeline_run = (
            db.query(PipelineRun)
            .filter(PipelineRun.iso_id == iso_obj.id, PipelineRun.status == "completed")
            .order_by(PipelineRun.completed_at.desc())
            .first()
        )

    # Get canonical DER profile
    der_profile_12x24 = get_der_profile(der_type)

    # Build location dict
    location = {
        "lat": lat,
        "lon": lon,
        "iso_code": iso_obj.iso_code if iso_obj else None,
        "zone_code": zone_obj.zone_code if zone_obj else None,
        "substation_name": nearest_sub.substation_name if nearest_sub else None,
        "ba_code": iso_obj.ba_code if iso_obj else None,
    }

    levels: list[GridLevelScore] = []

    def _build_level(
        level: str,
        name: Optional[str],
        constraint_loadshape: Optional[dict],
        score: Optional[float],
        score_label: str,
        tier: Optional[str],
    ) -> GridLevelScore:
        cf = None
        overlap = None
        if constraint_loadshape:
            cf = compute_coincidence_factor(der_type, constraint_loadshape)
            if der_profile_12x24 and cf is not None:
                overlap = elementwise_product_12x24(der_profile_12x24, constraint_loadshape)
        return GridLevelScore(
            level=level,
            name=name,
            constraint_loadshape=constraint_loadshape,
            grid_score=round(score, 4) if score is not None else None,
            score_label=score_label,
            tier=tier,
            coincidence_factor=cf,
            overlap_12x24=overlap,
        )

    # --- Substation level ---
    sub_loadshape = None
    sub_score = None
    sub_tier = None
    if nearest_sub:
        # Build 12x24 from SubstationLoadProfile rows
        slp_rows = (
            db.query(SubstationLoadProfile)
            .filter(SubstationLoadProfile.substation_id == nearest_sub.id)
            .all()
        )
        if slp_rows:
            sub_loadshape = {str(m): [0.0] * 24 for m in range(1, 13)}
            for row in slp_rows:
                sub_loadshape[str(row.month)][row.hour] = float(row.load_high_kw or 0)
            # Normalize to 0-1
            max_val = max(v for row in sub_loadshape.values() for v in row) or 1.0
            sub_loadshape = {
                k: [v / max_val for v in row]
                for k, row in sub_loadshape.items()
            }

        # Get hierarchy score for substation
        if pipeline_run:
            hs = (
                db.query(HierarchyScore)
                .filter(
                    HierarchyScore.pipeline_run_id == pipeline_run.id,
                    HierarchyScore.level == "substation",
                    HierarchyScore.entity_id == nearest_sub.id,
                )
                .first()
            )
            if hs:
                sub_score = hs.combined_score
                sub_tier = hs.constraint_tier
                if hs.constraint_loadshape:
                    sub_loadshape = hs.constraint_loadshape

        levels.append(_build_level(
            "substation",
            nearest_sub.substation_name,
            sub_loadshape,
            sub_score if sub_score is not None else (nearest_sub.peak_loading_pct / 100.0 if nearest_sub.peak_loading_pct else None),
            "Loading",
            sub_tier,
        ))

    # --- Pnode level ---
    if nearest_sub and nearest_sub.nearest_pnode_id and pipeline_run:
        ps = (
            db.query(PnodeScore)
            .filter(
                PnodeScore.pipeline_run_id == pipeline_run.id,
                PnodeScore.pnode_id == nearest_sub.nearest_pnode_id,
            )
            .first()
        )
        if ps:
            from app.models.pnode import Pnode
            pnode = db.get(Pnode, nearest_sub.nearest_pnode_id)
            levels.append(_build_level(
                "pnode",
                pnode.node_name if pnode else None,
                ps.constraint_loadshape,
                ps.severity_score,
                "Congestion Severity",
                ps.tier,
            ))
        else:
            levels.append(GridLevelScore(level="pnode", score_label="Congestion Severity"))
    else:
        levels.append(GridLevelScore(level="pnode", score_label="Congestion Severity"))

    # --- Zone level ---
    if zone_obj:
        zone_cp = (
            db.query(ConstraintProfile)
            .filter(
                ConstraintProfile.location_level == "zone",
                ConstraintProfile.location_id == zone_obj.id,
                ConstraintProfile.constraint_type == "congestion",
            )
            .order_by(ConstraintProfile.period_year.desc())
            .first()
        )

        zone_hs = None
        if pipeline_run:
            zone_hs = (
                db.query(HierarchyScore)
                .filter(
                    HierarchyScore.pipeline_run_id == pipeline_run.id,
                    HierarchyScore.level == "zone",
                    HierarchyScore.entity_id == zone_obj.id,
                )
                .first()
            )

        zone_loadshape = zone_cp.profile_12x24 if zone_cp else (zone_hs.constraint_loadshape if zone_hs else None)
        zone_score = zone_hs.combined_score if zone_hs else (zone_cp.severity_score if zone_cp else None)
        zone_tier = zone_hs.constraint_tier if zone_hs else (zone_cp.severity_tier if zone_cp else None)

        levels.append(_build_level(
            "zone",
            zone_obj.zone_code,
            zone_loadshape,
            zone_score,
            "Congestion",
            zone_tier,
        ))
    else:
        levels.append(GridLevelScore(level="zone", score_label="Congestion"))

    # --- Utility level ---
    # No direct substation-to-utility mapping; look for hosting capacity constraint profile
    utility_cp = None
    if nearest_sub:
        utility_cp = (
            db.query(ConstraintProfile)
            .filter(
                ConstraintProfile.location_level == "utility",
                ConstraintProfile.constraint_type == "capacity",
            )
            .first()
        )
    if utility_cp:
        levels.append(_build_level(
            "utility",
            None,
            utility_cp.profile_12x24,
            utility_cp.severity_score,
            "Hosting Capacity",
            utility_cp.severity_tier,
        ))
    else:
        levels.append(GridLevelScore(level="utility", score_label="Hosting Capacity"))

    # --- BA level ---
    ba_obj = None
    if iso_obj:
        # If the ISO itself is a BA (has ba_code), use it; otherwise look for child BAs
        if iso_obj.ba_code:
            ba_obj = iso_obj
        elif iso_obj.child_bas:
            ba_obj = iso_obj.child_bas[0]  # pick first child BA

    if ba_obj:
        cs = (
            db.query(CongestionScore)
            .filter(
                CongestionScore.ba_id == ba_obj.id,
                CongestionScore.period_type == "annual",
            )
            .order_by(CongestionScore.period_start.desc())
            .first()
        )
        ba_cp = (
            db.query(ConstraintProfile)
            .filter(
                ConstraintProfile.location_level == "ba",
                ConstraintProfile.location_id == ba_obj.id,
            )
            .order_by(ConstraintProfile.period_year.desc())
            .first()
        )
        ba_loadshape = ba_cp.profile_12x24 if ba_cp else None
        ba_score = cs.congestion_opportunity_score if cs else (ba_cp.severity_score if ba_cp else None)
        ba_tier = ba_cp.severity_tier if ba_cp else None

        levels.append(_build_level(
            "ba",
            ba_obj.ba_code or ba_obj.iso_code,
            ba_loadshape,
            ba_score,
            "Import Stress",
            ba_tier,
        ))
    else:
        levels.append(GridLevelScore(level="ba", score_label="Import Stress"))

    return DERGridScoresResponse(
        location=location,
        der_type=der_type,
        der_profile_12x24=der_profile_12x24,
        levels=levels,
    )
