"""
Unified constraint profile computation pipeline.

Replaces scattered logic in constraint_classifier.py, pnode_analyzer.py,
valuation_engine.py, congestion_calculator.py, and hierarchy_scorer.py with
a single coherent pipeline that produces constraint_profiles, intersections,
value stacks, and annotations.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app.models.computation_run import ComputationRun
from app.models.constraint_profile import ConstraintProfile
from app.models.constraint_annotation import ConstraintAnnotation
from app.models.der_profile import DERProfile
from app.models.constraint_der_intersection import ConstraintDERIntersection
from app.models.location_value_stack import LocationValueStack
from app.models.iso import ISO
from app.models.zone import Zone
from app.models.zone_lmp import ZoneLMP
from app.models.substation import Substation
from app.models.substation_load_profile import SubstationLoadProfile
from app.models.hosting_capacity import HostingCapacityRecord
from app.models.congestion import BAHourlyData, CongestionScore

from core.profile_utils import (
    flatten_12x24,
    sanitize_12x24,
    cosine_similarity,
    elementwise_product_12x24,
    profile_summary_stats,
    normalize_min_max,
    severity_tier,
    value_tier,
    compute_overlap_hours,
)

logger = logging.getLogger(__name__)

# ============================================================
# Constants (preserved from existing codebase)
# ============================================================

# Congestion thresholds
CONGESTION_THRESHOLD_DOLLARS = 2.0
ENERGY_DEVIATION_THRESHOLD = 3.0
PEAK_HOURS = range(7, 23)

# Zone severity weights (from constraint_classifier.py)
ZONE_WEIGHTS = {
    "congestion_ratio": 0.30,
    "congestion_volatility": 0.25,
    "congested_hours_pct": 0.25,
    "peak_offpeak_ratio": 0.20,
}

# Pnode severity weights (from pnode_analyzer.py)
PNODE_WEIGHTS = {
    "magnitude": 0.30,
    "volatility": 0.20,
    "congested_hours": 0.25,
    "peak_offpeak": 0.15,
    "extreme_events": 0.10,
}

# Severity tier cutoffs
TIER_CRITICAL = 0.75
TIER_ELEVATED = 0.50
TIER_MODERATE = 0.25

# Valuation constants (from valuation_engine.py)
AVOIDED_CAPACITY_COST_PER_KW_YEAR = 80.0
AVOIDED_FEEDER_COST_PER_KW_YEAR = 50.0
SUBSTATION_LOADING_THRESHOLD = 0.80
LOADING_FACTOR_RANGE = 0.40

# Value tier thresholds ($/kW-yr)
VALUE_PREMIUM = 150.0
VALUE_HIGH = 80.0
VALUE_MODERATE = 30.0


# ============================================================
# Step 2.1.1: Zone Congestion Profile Builder
# ============================================================

def build_zone_congestion_profiles(
    session: Session,
    iso_id: int,
    year: int,
    run: ComputationRun,
) -> list[ConstraintProfile]:
    """Build 12x24 congestion profiles for all zones in an ISO."""
    zones = session.query(Zone).filter_by(iso_id=iso_id).all()
    if not zones:
        logger.warning(f"No zones found for iso_id={iso_id}")
        return []

    year_start = f"{year}-01-01"
    year_end = f"{year + 1}-01-01"

    profiles = []
    raw_scores = []

    for zone in zones:
        # Aggregate LMP data into 12x24
        rows = (
            session.query(
                ZoneLMP.month,
                ZoneLMP.hour_local,
                func.avg(func.abs(ZoneLMP.congestion)).label("avg_intensity"),
                func.max(func.abs(ZoneLMP.congestion)).label("max_intensity"),
                func.count().filter(
                    func.abs(ZoneLMP.congestion) > CONGESTION_THRESHOLD_DOLLARS
                ).label("congested_count"),
                func.count().label("total_count"),
            )
            .filter(
                ZoneLMP.zone_id == zone.id,
                ZoneLMP.timestamp_utc >= year_start,
                ZoneLMP.timestamp_utc < year_end,
            )
            .group_by(ZoneLMP.month, ZoneLMP.hour_local)
            .order_by(ZoneLMP.month, ZoneLMP.hour_local)
            .all()
        )

        if not rows:
            continue

        # Build 12x24 profile
        profile_12x24 = {str(m): [0.0] * 24 for m in range(1, 13)}
        total_congested = 0
        total_hours = 0

        for row in rows:
            m_key = str(row.month)
            if 0 <= row.hour_local < 24:
                profile_12x24[m_key][row.hour_local] = round(float(row.avg_intensity), 4)
                total_congested += int(row.congested_count)
                total_hours += int(row.total_count)

        # Compute zone-level metrics for severity scoring
        all_lmps = (
            session.query(
                ZoneLMP.congestion,
                ZoneLMP.lmp,
                ZoneLMP.hour_local,
            )
            .filter(
                ZoneLMP.zone_id == zone.id,
                ZoneLMP.timestamp_utc >= year_start,
                ZoneLMP.timestamp_utc < year_end,
            )
            .all()
        )

        if not all_lmps:
            continue

        cong_values = [abs(r.congestion) for r in all_lmps if r.congestion is not None]
        lmp_values = [abs(r.lmp) for r in all_lmps if r.lmp is not None and r.lmp != 0]

        if not cong_values or not lmp_values:
            continue

        import statistics
        avg_cong = statistics.mean(cong_values)
        std_cong = statistics.stdev(cong_values) if len(cong_values) > 1 else 0.0
        avg_lmp = statistics.mean(lmp_values)

        # Four metrics (from constraint_classifier.py)
        congestion_ratio = avg_cong / avg_lmp if avg_lmp > 0 else 0.0
        congestion_volatility = std_cong / avg_cong if avg_cong > 0 else 0.0
        congested_hours_pct = total_congested / total_hours if total_hours > 0 else 0.0

        peak_cong = [abs(r.congestion) for r in all_lmps
                     if r.congestion is not None and r.hour_local in PEAK_HOURS]
        offpeak_cong = [abs(r.congestion) for r in all_lmps
                        if r.congestion is not None and r.hour_local not in PEAK_HOURS]
        avg_peak = statistics.mean(peak_cong) if peak_cong else 0.0
        avg_offpeak = statistics.mean(offpeak_cong) if offpeak_cong else 0.001
        peak_offpeak_ratio = avg_peak / avg_offpeak if avg_offpeak > 0 else 1.0

        # Weighted score (raw, before normalization)
        raw_score = (
            ZONE_WEIGHTS["congestion_ratio"] * min(congestion_ratio, 1.0) +
            ZONE_WEIGHTS["congestion_volatility"] * min(congestion_volatility / 3.0, 1.0) +
            ZONE_WEIGHTS["congested_hours_pct"] * min(congested_hours_pct, 1.0) +
            ZONE_WEIGHTS["peak_offpeak_ratio"] * min(peak_offpeak_ratio / 5.0, 1.0)
        )

        profile_12x24 = sanitize_12x24(profile_12x24)
        stats = profile_summary_stats(profile_12x24, threshold=CONGESTION_THRESHOLD_DOLLARS)

        # Economic value
        congested_lmps = [abs(r.congestion) for r in all_lmps
                          if r.congestion is not None
                          and abs(r.congestion) > CONGESTION_THRESHOLD_DOLLARS]
        avg_marginal_cost = statistics.mean(congested_lmps) if congested_lmps else 0.0
        annual_cost = avg_marginal_cost * len(congested_lmps)

        raw_scores.append((zone, raw_score, profile_12x24, stats,
                           avg_marginal_cost, annual_cost, congested_hours_pct))

    # Normalize severity scores across zones in this ISO
    if not raw_scores:
        return []

    all_raw = [s[1] for s in raw_scores]
    normalized = normalize_min_max(all_raw)

    for (zone, raw_score, p12x24, stats, avg_mc, ann_cost, chp), norm_score in zip(raw_scores, normalized):
        profile = ConstraintProfile(
            location_level="zone",
            location_id=zone.id,
            constraint_type="congestion",
            source_type="lmp_zone",
            period_year=year,
            profile_12x24=p12x24,
            peak_intensity=stats["peak_intensity"],
            peak_month=stats["peak_month"],
            peak_hour=stats["peak_hour"],
            mean_intensity=stats["mean_intensity"],
            total_constrained_hours=stats["total_constrained_hours"],
            constrained_hours_pct=round(chp, 4),
            severity_score=round(norm_score, 4),
            severity_tier=severity_tier(norm_score),
            avg_marginal_cost=round(avg_mc, 2),
            annual_cost=round(ann_cost, 2),
            computation_run_id=run.id,
        )
        session.merge(profile)
        profiles.append(profile)

    session.flush()
    logger.info(f"Built {len(profiles)} zone congestion profiles for iso_id={iso_id}")
    return profiles


# ============================================================
# Step 2.1.3: Substation Loading Profile Builder
# ============================================================

def build_substation_loading_profiles(
    session: Session,
    iso_id: int,
    run: ComputationRun,
) -> list[ConstraintProfile]:
    """Build 12x24 loading profiles for substations with load profile data."""
    substations = (
        session.query(Substation)
        .filter_by(iso_id=iso_id)
        .filter(Substation.facility_rating_mw.isnot(None))
        .filter(Substation.facility_rating_mw > 0)
        .all()
    )

    profiles = []
    for sub in substations:
        load_profiles = (
            session.query(SubstationLoadProfile)
            .filter_by(substation_id=sub.id)
            .all()
        )
        if not load_profiles:
            continue

        rating_kw = sub.facility_rating_mw * 1000.0
        profile_12x24 = {str(m): [0.0] * 24 for m in range(1, 13)}

        for lp in load_profiles:
            m_key = str(lp.month)
            if 0 <= lp.hour < 24:
                loading_pct = lp.load_high_kw / rating_kw if rating_kw > 0 else 0.0
                profile_12x24[m_key][lp.hour] = round(loading_pct, 4)

        profile_12x24 = sanitize_12x24(profile_12x24)
        stats = profile_summary_stats(profile_12x24, threshold=SUBSTATION_LOADING_THRESHOLD)

        # Severity based on peak loading
        peak_pct = sub.peak_loading_pct if sub.peak_loading_pct else stats["peak_intensity"] * 100
        if peak_pct >= 100:
            sev_score = 1.0
        elif peak_pct >= 90:
            sev_score = 0.75 + (peak_pct - 90) / 40.0
        elif peak_pct >= 80:
            sev_score = 0.50 + (peak_pct - 80) / 40.0
        else:
            sev_score = peak_pct / 160.0

        sev_score = min(1.0, max(0.0, sev_score))

        # Economic value
        loading_factor = min(1.0, max(0.0, (peak_pct - 80) / 40.0)) if peak_pct > 80 else 0.0
        avg_mc = AVOIDED_CAPACITY_COST_PER_KW_YEAR * loading_factor
        annual_cost = avg_mc * sub.facility_rating_mw * 1000 if loading_factor > 0 else 0.0

        # Use current year since loading data is typically current
        period_year = datetime.now().year

        profile = ConstraintProfile(
            location_level="substation",
            location_id=sub.id,
            constraint_type="loading",
            source_type="grip",
            period_year=period_year,
            profile_12x24=profile_12x24,
            peak_intensity=stats["peak_intensity"],
            peak_month=stats["peak_month"],
            peak_hour=stats["peak_hour"],
            mean_intensity=stats["mean_intensity"],
            total_constrained_hours=stats["total_constrained_hours"],
            constrained_hours_pct=stats["constrained_hours_pct"],
            severity_score=round(sev_score, 4),
            severity_tier=severity_tier(sev_score),
            avg_marginal_cost=round(avg_mc, 2),
            annual_cost=round(annual_cost, 2),
            computation_run_id=run.id,
        )
        session.merge(profile)
        profiles.append(profile)

    session.flush()
    logger.info(f"Built {len(profiles)} substation loading profiles for iso_id={iso_id}")
    return profiles


# ============================================================
# Step 2.1.4: Feeder Capacity Profile Builder
# ============================================================

def build_feeder_capacity_profiles(
    session: Session,
    iso_id: int,
    run: ComputationRun,
) -> list[ConstraintProfile]:
    """Build capacity profiles for feeders with hosting capacity data."""
    from app.models.feeder import Feeder

    feeders = (
        session.query(Feeder, Substation)
        .join(Substation, Feeder.substation_id == Substation.id)
        .filter(Substation.iso_id == iso_id)
        .all()
    )

    profiles = []
    for feeder, sub in feeders:
        # Get hosting capacity for this feeder
        hc_record = (
            session.query(HostingCapacityRecord)
            .filter_by(feeder_name=feeder.feeder_id_external)
            .first()
        )
        if not hc_record:
            continue

        # Compute utilization
        total_cap = hc_record.hosting_capacity_mw or 0
        if total_cap <= 0:
            continue
        remaining = hc_record.remaining_capacity_mw or total_cap
        utilization = 1.0 - (remaining / total_cap)

        # Try to use parent substation's temporal pattern
        sub_load_profiles = (
            session.query(SubstationLoadProfile)
            .filter_by(substation_id=sub.id)
            .all()
        )

        period_year = datetime.now().year
        profile_12x24 = {str(m): [0.0] * 24 for m in range(1, 13)}

        if sub_load_profiles:
            rating_kw = sub.facility_rating_mw * 1000.0 if sub.facility_rating_mw else 1.0
            for lp in sub_load_profiles:
                m_key = str(lp.month)
                if 0 <= lp.hour < 24:
                    loading_pct = lp.load_high_kw / rating_kw if rating_kw > 0 else 0.0
                    profile_12x24[m_key][lp.hour] = round(loading_pct * utilization, 4)
        else:
            # Flat profile scaled by utilization
            profile_12x24 = {str(m): [round(utilization, 4)] * 24 for m in range(1, 13)}

        profile_12x24 = sanitize_12x24(profile_12x24)
        stats = profile_summary_stats(profile_12x24, threshold=0.7)

        # Severity based on remaining capacity
        remaining_pct = remaining / total_cap if total_cap > 0 else 1.0
        if remaining_pct <= 0.05:
            sev_score = 1.0
        elif remaining_pct <= 0.15:
            sev_score = 0.75
        elif remaining_pct <= 0.30:
            sev_score = 0.50
        else:
            sev_score = max(0.0, 0.25 * (1.0 - remaining_pct))

        avg_mc = AVOIDED_FEEDER_COST_PER_KW_YEAR * utilization

        profile = ConstraintProfile(
            location_level="feeder",
            location_id=feeder.id,
            constraint_type="capacity",
            source_type="hosting_capacity",
            period_year=period_year,
            profile_12x24=profile_12x24,
            peak_intensity=stats["peak_intensity"],
            peak_month=stats["peak_month"],
            peak_hour=stats["peak_hour"],
            mean_intensity=stats["mean_intensity"],
            total_constrained_hours=stats["total_constrained_hours"],
            constrained_hours_pct=stats["constrained_hours_pct"],
            severity_score=round(sev_score, 4),
            severity_tier=severity_tier(sev_score),
            avg_marginal_cost=round(avg_mc, 2),
            annual_cost=round(avg_mc * total_cap * 1000, 2),
            computation_run_id=run.id,
        )
        session.merge(profile)
        profiles.append(profile)

    session.flush()
    logger.info(f"Built {len(profiles)} feeder capacity profiles for iso_id={iso_id}")
    return profiles


# ============================================================
# Step 2.1.5: BA Import Stress Profile Builder
# ============================================================

def build_ba_import_stress_profiles(
    session: Session,
    year: int,
    run: ComputationRun,
) -> list[ConstraintProfile]:
    """Build 12x24 import stress profiles for all BAs."""
    bas = (
        session.query(ISO)
        .filter(ISO.ba_code.isnot(None), ISO.is_rto == False)
        .filter(ISO.transfer_limit_mw.isnot(None))
        .filter(ISO.transfer_limit_mw > 0)
        .all()
    )

    year_start = f"{year}-01-01"
    year_end = f"{year + 1}-01-01"

    profiles = []
    raw_scores = []

    for ba in bas:
        rows = (
            session.query(
                func.extract("month", BAHourlyData.timestamp_utc).label("month"),
                func.extract("hour", BAHourlyData.timestamp_utc).label("hour"),
                func.avg(
                    func.greatest(BAHourlyData.net_imports_mw, 0) / ba.transfer_limit_mw
                ).label("avg_utilization"),
                func.count().filter(
                    BAHourlyData.net_imports_mw / ba.transfer_limit_mw > 0.80
                ).label("hours_above_80"),
            )
            .filter(
                BAHourlyData.ba_id == ba.id,
                BAHourlyData.timestamp_utc >= year_start,
                BAHourlyData.timestamp_utc < year_end,
                BAHourlyData.net_imports_mw.isnot(None),
            )
            .group_by(
                func.extract("month", BAHourlyData.timestamp_utc),
                func.extract("hour", BAHourlyData.timestamp_utc),
            )
            .all()
        )

        if not rows:
            continue

        profile_12x24 = {str(m): [0.0] * 24 for m in range(1, 13)}
        total_above_80 = 0

        for row in rows:
            m_key = str(int(row.month))
            h = int(row.hour)
            if 0 <= h < 24:
                profile_12x24[m_key][h] = round(float(row.avg_utilization or 0), 4)
                total_above_80 += int(row.hours_above_80 or 0)

        profile_12x24 = sanitize_12x24(profile_12x24)
        stats = profile_summary_stats(profile_12x24, threshold=0.80)

        # Get existing CongestionScore for economic metrics
        existing_score = (
            session.query(CongestionScore)
            .filter_by(ba_id=ba.id, period_type="year")
            .filter(CongestionScore.period_start >= year_start)
            .first()
        )

        avg_mc = 0.0
        if existing_score and existing_score.avg_congestion_premium:
            avg_mc = existing_score.avg_congestion_premium

        # Raw severity based on hours above thresholds
        hours_total = sum(int(row.hours_above_80 or 0) for row in rows)
        raw_score = min(1.0, hours_total / 500.0)  # 500 hours ≈ critical

        raw_scores.append((ba, raw_score, profile_12x24, stats, avg_mc))

    if not raw_scores:
        return []

    all_raw = [s[1] for s in raw_scores]
    normalized = normalize_min_max(all_raw)

    for (ba, raw, p12x24, stats, avg_mc), norm_score in zip(raw_scores, normalized):
        profile = ConstraintProfile(
            location_level="ba",
            location_id=ba.id,
            constraint_type="import_stress",
            source_type="eia930",
            period_year=year,
            profile_12x24=p12x24,
            peak_intensity=stats["peak_intensity"],
            peak_month=stats["peak_month"],
            peak_hour=stats["peak_hour"],
            mean_intensity=stats["mean_intensity"],
            total_constrained_hours=stats["total_constrained_hours"],
            constrained_hours_pct=stats["constrained_hours_pct"],
            severity_score=round(norm_score, 4),
            severity_tier=severity_tier(norm_score),
            avg_marginal_cost=round(avg_mc, 2) if avg_mc else None,
            annual_cost=None,
            computation_run_id=run.id,
        )
        session.merge(profile)
        profiles.append(profile)

    session.flush()
    logger.info(f"Built {len(profiles)} BA import stress profiles")
    return profiles


# ============================================================
# Step 2.2: Intersection Computer
# ============================================================

def compute_intersections(
    session: Session,
    run: ComputationRun,
) -> int:
    """Compute intersections between constraint profiles and all canonical DER profiles."""
    # Get constraint profiles from this run
    constraint_profiles = (
        session.query(ConstraintProfile)
        .filter_by(computation_run_id=run.id)
        .all()
    )

    # Get canonical DER profiles
    der_profiles = (
        session.query(DERProfile)
        .filter_by(profile_source="canonical")
        .all()
    )

    if not constraint_profiles or not der_profiles:
        return 0

    count = 0
    for cp in constraint_profiles:
        for dp in der_profiles:
            # Compute coincidence factor
            if dp.is_dispatchable:
                coincidence = 1.0
                overlap = compute_overlap_hours(cp.profile_12x24, None,
                                                threshold_a=CONGESTION_THRESHOLD_DOLLARS)
                overlap_profile = None
            else:
                cp_vec = flatten_12x24(cp.profile_12x24)
                dp_vec = flatten_12x24(dp.profile_12x24)
                coincidence = cosine_similarity(cp_vec, dp_vec)
                overlap = compute_overlap_hours(
                    cp.profile_12x24, dp.profile_12x24,
                    threshold_a=0.0, threshold_b=0.1)
                overlap_profile = sanitize_12x24(elementwise_product_12x24(cp.profile_12x24, dp.profile_12x24))

            # Value computation
            base_cost = cp.avg_marginal_cost or 0.0
            constrained_fraction = cp.constrained_hours_pct
            val = base_cost * coincidence * constrained_fraction
            val = round(val, 2)

            intersection = ConstraintDERIntersection(
                constraint_profile_id=cp.id,
                der_profile_id=dp.id,
                coincidence_factor=round(coincidence, 4),
                overlap_hours=overlap,
                overlap_12x24=overlap_profile,
                value_per_kw_year=val,
                value_tier=value_tier(val),
            )
            session.merge(intersection)
            count += 1

    session.flush()
    logger.info(f"Computed {count} constraint-DER intersections")
    return count


# ============================================================
# Step 2.3: Value Stacker
# ============================================================

def compute_value_stacks(
    session: Session,
    run: ComputationRun,
) -> int:
    """Compute value stacks across all constraint layers for each location."""
    der_profiles = (
        session.query(DERProfile)
        .filter_by(profile_source="canonical")
        .all()
    )

    if not der_profiles:
        return 0

    # Get all unique locations from constraint profiles in this run
    locations = (
        session.query(
            ConstraintProfile.location_level,
            ConstraintProfile.location_id,
            ConstraintProfile.period_year,
        )
        .filter_by(computation_run_id=run.id)
        .distinct()
        .all()
    )

    count = 0
    for level, loc_id, period_year in locations:
        # Get all constraint profiles at this location
        loc_profiles = (
            session.query(ConstraintProfile)
            .filter_by(location_level=level, location_id=loc_id, period_year=period_year)
            .all()
        )

        for dp in der_profiles:
            congestion_val = 0.0
            loading_val = 0.0
            capacity_val = 0.0
            import_stress_val = 0.0
            coincidence_sum = 0.0
            coincidence_count = 0
            layers = []

            for cp in loc_profiles:
                intersection = (
                    session.query(ConstraintDERIntersection)
                    .filter_by(constraint_profile_id=cp.id, der_profile_id=dp.id)
                    .first()
                )

                if not intersection:
                    continue

                val = intersection.value_per_kw_year

                if cp.constraint_type == "congestion":
                    congestion_val += val
                elif cp.constraint_type == "loading":
                    loading_val += val
                elif cp.constraint_type == "capacity":
                    capacity_val += val
                elif cp.constraint_type == "import_stress":
                    import_stress_val += val

                coincidence_sum += intersection.coincidence_factor
                coincidence_count += 1
                layers.append({
                    "type": cp.constraint_type,
                    "profile_id": cp.id,
                    "value": val,
                })

            total = congestion_val + loading_val + capacity_val + import_stress_val
            composite_cf = coincidence_sum / coincidence_count if coincidence_count > 0 else 0.0

            # Add contribution percentages
            for layer in layers:
                layer["contribution_pct"] = round(layer["value"] / total * 100, 1) if total > 0 else 0.0

            stack = LocationValueStack(
                location_level=level,
                location_id=loc_id,
                der_profile_id=dp.id,
                congestion_value_per_kw_year=round(congestion_val, 2),
                loading_value_per_kw_year=round(loading_val, 2),
                capacity_value_per_kw_year=round(capacity_val, 2),
                import_stress_value_per_kw_year=round(import_stress_val, 2),
                total_value_per_kw_year=round(total, 2),
                composite_coincidence_factor=round(composite_cf, 4),
                value_tier=value_tier(total),
                constraint_layers=layers,
                period_year=period_year,
            )
            session.merge(stack)
            count += 1

    session.flush()
    logger.info(f"Computed {count} location value stacks")
    return count


# ============================================================
# Step 2.4: Annotation Linker
# ============================================================

def link_annotations(
    session: Session,
    run: ComputationRun,
) -> int:
    """Link existing regulatory data to constraint profiles."""
    from app.models.grid_constraint import GridConstraint
    from app.models.load_forecast import LoadForecast
    from app.models.resource_need import ResourceNeed
    from app.models.filing import Filing

    count = 0

    # Link grid constraints
    grid_constraints = session.query(GridConstraint).all()
    for gc in grid_constraints:
        # Find constraint profiles for zones served by this utility
        profiles = (
            session.query(ConstraintProfile)
            .filter_by(location_level="zone", computation_run_id=run.id)
            .all()
        )
        for cp in profiles:
            annotation = ConstraintAnnotation(
                constraint_profile_id=cp.id,
                annotation_type="grid_plan",
                utility_id=gc.utility_id,
                title=gc.constraint_name or f"Grid constraint: {gc.constraint_type}",
                summary=gc.description,
                planned_solution=gc.planned_mitigation,
                deferral_value_estimate=gc.estimated_cost,
                confidence=0.7,
            )
            session.add(annotation)
            count += 1
            break  # One annotation per constraint, linked to first matching profile

    # Link load forecasts with high growth
    load_forecasts = (
        session.query(LoadForecast)
        .filter(LoadForecast.growth_rate_pct > 2.0)
        .all()
    )
    for lf in load_forecasts:
        profiles = (
            session.query(ConstraintProfile)
            .filter_by(location_level="zone", computation_run_id=run.id)
            .all()
        )
        for cp in profiles:
            annotation = ConstraintAnnotation(
                constraint_profile_id=cp.id,
                annotation_type="grid_plan",
                utility_id=lf.utility_id,
                title=f"High load growth: {lf.growth_rate_pct:.1f}% annual",
                summary=f"Forecast area: {lf.area_name or 'utility-wide'}. "
                         f"Peak demand: {lf.peak_demand_mw or 'N/A'} MW.",
                confidence=0.6,
            )
            session.add(annotation)
            count += 1
            break

    # Link resource needs
    resource_needs = session.query(ResourceNeed).all()
    for rn in resource_needs:
        profiles = (
            session.query(ConstraintProfile)
            .filter_by(location_level="zone", computation_run_id=run.id)
            .all()
        )
        for cp in profiles:
            annotation = ConstraintAnnotation(
                constraint_profile_id=cp.id,
                annotation_type="resource_need",
                utility_id=rn.utility_id,
                title=f"Resource need: {rn.need_mw or 'N/A'} MW",
                summary=f"Eligible types: {rn.eligible_resource_types or 'various'}",
                confidence=0.6,
            )
            session.add(annotation)
            count += 1
            break

    # Link IRP/DRP filings
    filings = (
        session.query(Filing)
        .filter(Filing.filing_type.in_(["irp", "drp", "grid_mod"]))
        .all()
    )
    for filing in filings:
        profiles = (
            session.query(ConstraintProfile)
            .filter_by(location_level="zone", computation_run_id=run.id)
            .all()
        )
        for cp in profiles:
            annotation = ConstraintAnnotation(
                constraint_profile_id=cp.id,
                annotation_type="irp_citation",
                utility_id=filing.utility_id,
                filing_id=filing.id,
                title=filing.title or f"{filing.filing_type.upper()} filing",
                summary=filing.summary,
                source_url=filing.source_url,
                source_document=filing.docket_number,
                confidence=0.8,
            )
            session.add(annotation)
            count += 1
            break

    session.flush()
    logger.info(f"Linked {count} annotations to constraint profiles")
    return count


# ============================================================
# Step 2.5: Materialized View Refresh
# ============================================================

def refresh_materialized_views(session: Session):
    """Refresh materialized views after computation."""
    try:
        session.execute(text("REFRESH MATERIALIZED VIEW mv_zone_constraint_summary"))
        session.execute(text("REFRESH MATERIALIZED VIEW mv_location_rankings"))
        session.commit()
        logger.info("Refreshed materialized views")
    except Exception as e:
        logger.warning(f"Could not refresh materialized views: {e}")
        session.rollback()


# ============================================================
# Full Pipeline Orchestrator
# ============================================================

def run_full_pipeline(
    session: Session,
    iso_code: Optional[str] = None,
    year: int = 2024,
    only: Optional[str] = None,
    skip_intersections: bool = False,
    skip_stacks: bool = False,
    skip_annotations: bool = False,
) -> ComputationRun:
    """Run the full computation pipeline.

    Args:
        session: DB session
        iso_code: ISO code to compute for (None = all ISOs + all BAs)
        year: Period year
        only: Only run a specific builder (congestion, loading, capacity, import_stress)
        skip_intersections: Skip intersection computation
        skip_stacks: Skip value stack computation
        skip_annotations: Skip annotation linking

    Returns:
        ComputationRun record
    """
    run = ComputationRun(
        run_type="full_recompute" if not only else only,
        period_year=year,
        status="running",
    )
    session.add(run)
    session.flush()

    total_profiles = 0

    try:
        if iso_code:
            iso = session.query(ISO).filter(
                func.lower(ISO.iso_code) == iso_code.lower()
            ).order_by(ISO.id).first()
            if not iso:
                raise ValueError(f"ISO '{iso_code}' not found")
            run.iso_id = iso.id
            isos = [iso]
        else:
            isos = session.query(ISO).filter_by(is_rto=True).all()

        # Build constraint profiles
        for iso in isos:
            if not only or only == "congestion":
                profiles = build_zone_congestion_profiles(session, iso.id, year, run)
                total_profiles += len(profiles)

            if not only or only == "loading":
                profiles = build_substation_loading_profiles(session, iso.id, run)
                total_profiles += len(profiles)

            if not only or only == "capacity":
                profiles = build_feeder_capacity_profiles(session, iso.id, run)
                total_profiles += len(profiles)

        # BA import stress (not per-ISO)
        if not only or only == "import_stress":
            profiles = build_ba_import_stress_profiles(session, year, run)
            total_profiles += len(profiles)

        # Compute intersections
        intersections = 0
        if not skip_intersections:
            intersections = compute_intersections(session, run)

        # Compute value stacks
        stacks = 0
        if not skip_stacks:
            stacks = compute_value_stacks(session, run)

        # Link annotations
        annotations = 0
        if not skip_annotations:
            annotations = link_annotations(session, run)

        # Refresh materialized views
        refresh_materialized_views(session)

        run.status = "success"
        run.completed_at = datetime.now(timezone.utc)
        run.metrics_json = {
            "profiles_created": total_profiles,
            "intersections_created": intersections,
            "value_stacks_created": stacks,
            "annotations_linked": annotations,
        }

        session.commit()
        logger.info(
            f"Pipeline complete: {total_profiles} profiles, "
            f"{intersections} intersections, {stacks} value stacks, "
            f"{annotations} annotations"
        )

    except Exception as e:
        run.status = "failed"
        run.error_message = str(e)
        run.completed_at = datetime.now(timezone.utc)
        session.commit()
        logger.error(f"Pipeline failed: {e}")
        raise

    return run
