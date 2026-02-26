"""
DER Valuation Engine: computes constraint-relief dollar value for DERs.

Calculates the value of placing a DER at a specific location in the grid
hierarchy, from zone level down to circuit level. Three inputs drive value:
1. Constraint intensity at the location (LMP congestion + distribution loading)
2. Coincidence factor between DER output profile and constraint loadshape
3. DER capacity (MW)
"""

import logging
from dataclasses import dataclass
from typing import Optional

from sqlalchemy.orm import Session

from app.models import (
    ZoneClassification, PnodeScore, Substation, Pnode,
    PipelineRun, Feeder,
)
from core.der_profiles import compute_coincidence_factor, get_eac_category
from core.geo_resolver import GeoResolution

logger = logging.getLogger(__name__)

# Default avoided cost assumptions ($/kW-year)
DEFAULT_AVOIDED_CAPACITY_COST = 80.0  # $/kW-yr for substation upgrade deferral
DEFAULT_AVOIDED_FEEDER_COST = 50.0    # $/kW-yr for feeder upgrade deferral

# Hours in a year
HOURS_PER_YEAR = 8760

# Value tier thresholds ($/kW-year)
DEFAULT_TIER_THRESHOLDS = {
    "premium": 150.0,
    "high": 80.0,
    "moderate": 30.0,
}


@dataclass
class ValuationResult:
    """Output of a DER valuation computation."""
    zone_congestion_value: float = 0.0
    pnode_multiplier: float = 1.0
    substation_loading_value: float = 0.0
    feeder_capacity_value: float = 0.0
    total_constraint_relief_value: float = 0.0
    coincidence_factor: float = 0.0
    effective_capacity_mw: float = 0.0
    value_tier: str = "low"
    value_per_kw_year: float = 0.0
    value_breakdown: dict = None

    def __post_init__(self):
        if self.value_breakdown is None:
            self.value_breakdown = {}


def compute_der_value(
    db: Session,
    resolution: GeoResolution,
    der_type: str,
    capacity_mw: float,
    pipeline_run_id: Optional[int] = None,
    iso_config: Optional[dict] = None,
) -> ValuationResult:
    """
    Compute the constraint-relief value of a DER at a resolved location.

    Args:
        db: Database session
        resolution: GeoResolution from geo_resolver.resolve()
        der_type: DER type key (e.g. "solar", "storage")
        capacity_mw: DER nameplate capacity in MW
        pipeline_run_id: Specific pipeline run to use (defaults to latest completed)
        iso_config: Optional ISO-specific config overrides

    Returns:
        ValuationResult with per-level values and composite total.
    """
    result = ValuationResult()
    config = iso_config or {}

    # Resolve pipeline run
    run = _get_pipeline_run(db, resolution.iso_id, pipeline_run_id)
    if not run:
        logger.warning("No completed pipeline run found for valuation")
        return result

    # Get constraint loadshape for coincidence factor computation
    constraint_loadshape = _get_constraint_loadshape(
        db, run.id, resolution.zone_id, resolution.nearest_pnode_id,
    )

    # Coincidence factor
    cf = compute_coincidence_factor(der_type, constraint_loadshape)
    result.coincidence_factor = cf
    result.effective_capacity_mw = round(capacity_mw * cf, 4)

    # Zone-level congestion value
    zone_value = _compute_zone_value(
        db, run.id, resolution.zone_id, cf, capacity_mw,
    )
    result.zone_congestion_value = zone_value

    # Pnode multiplier (location premium/discount vs zone average)
    pnode_mult = _compute_pnode_multiplier(
        db, run.id, resolution.zone_id, resolution.nearest_pnode_id,
    )
    result.pnode_multiplier = pnode_mult

    # Substation loading value
    sub_value = _compute_substation_value(
        db, resolution.substation_id, cf, capacity_mw, config,
    )
    result.substation_loading_value = sub_value

    # Feeder capacity value (Phase 2, returns 0 if no feeder data)
    feeder_value = _compute_feeder_value(
        db, resolution.feeder_id, cf, capacity_mw, config,
    )
    result.feeder_capacity_value = feeder_value

    # Composite value
    total = (zone_value * pnode_mult) + sub_value + feeder_value
    result.total_constraint_relief_value = round(total, 2)

    # Value per kW-year
    capacity_kw = capacity_mw * 1000
    if capacity_kw > 0:
        result.value_per_kw_year = round(total / capacity_kw, 2)

    # Value tier
    tier_thresholds = config.get("tier_thresholds", DEFAULT_TIER_THRESHOLDS)
    result.value_tier = _assign_value_tier(result.value_per_kw_year, tier_thresholds)

    # Breakdown
    result.value_breakdown = {
        "zone_congestion": round(zone_value, 2),
        "pnode_multiplier": round(pnode_mult, 4),
        "zone_adjusted": round(zone_value * pnode_mult, 2),
        "substation_loading": round(sub_value, 2),
        "feeder_capacity": round(feeder_value, 2),
        "total": result.total_constraint_relief_value,
        "coincidence_factor": cf,
        "effective_capacity_mw": result.effective_capacity_mw,
        "der_type": der_type,
        "eac_category": get_eac_category(der_type),
        "value_per_kw_year": result.value_per_kw_year,
        "value_tier": result.value_tier,
    }

    return result


def _get_pipeline_run(
    db: Session, iso_id: Optional[int], pipeline_run_id: Optional[int],
) -> Optional[PipelineRun]:
    """Get the pipeline run to use for valuation data."""
    if pipeline_run_id:
        return db.query(PipelineRun).get(pipeline_run_id)

    if not iso_id:
        return None

    return (
        db.query(PipelineRun)
        .filter(PipelineRun.iso_id == iso_id, PipelineRun.status == "completed")
        .order_by(PipelineRun.completed_at.desc())
        .first()
    )


def _get_constraint_loadshape(
    db: Session,
    pipeline_run_id: int,
    zone_id: Optional[int],
    pnode_id: Optional[int],
) -> Optional[dict]:
    """Get the best available constraint loadshape (pnode > zone average)."""
    # Try pnode-level loadshape first
    if pnode_id:
        score = db.query(PnodeScore).filter(
            PnodeScore.pipeline_run_id == pipeline_run_id,
            PnodeScore.pnode_id == pnode_id,
        ).first()
        if score and score.constraint_loadshape:
            return score.constraint_loadshape

    # Fallback: average loadshape across zone pnodes
    if zone_id:
        scores = (
            db.query(PnodeScore)
            .join(Pnode)
            .filter(
                PnodeScore.pipeline_run_id == pipeline_run_id,
                Pnode.zone_id == zone_id,
                PnodeScore.constraint_loadshape.isnot(None),
            )
            .limit(50)  # cap for performance
            .all()
        )
        if scores:
            valid = [s.constraint_loadshape for s in scores if s.constraint_loadshape]
            if valid:
                return _average_loadshapes(valid)

    return None


def _average_loadshapes(loadshapes: list[dict]) -> dict:
    """Average multiple 12x24 loadshapes."""
    n = len(loadshapes)
    if n == 0:
        return {}
    if n == 1:
        return loadshapes[0]

    result = {}
    for month in range(1, 13):
        m_key = str(month)
        avg_row = [0.0] * 24
        count = 0
        for ls in loadshapes:
            row = ls.get(m_key, [])
            if len(row) == 24:
                for h in range(24):
                    avg_row[h] += row[h]
                count += 1
        if count > 0:
            result[m_key] = [round(v / count, 4) for v in avg_row]
        else:
            result[m_key] = [0.0] * 24

    return result


def _compute_zone_value(
    db: Session,
    pipeline_run_id: int,
    zone_id: Optional[int],
    coincidence_factor: float,
    capacity_mw: float,
) -> float:
    """
    Zone-level congestion value.

    Formula: avg_abs_congestion * congested_hours * coincidence * capacity_mw
    Units: $/MWh * hours * unitless * MW = $/year
    """
    if not zone_id:
        return 0.0

    cls = db.query(ZoneClassification).filter(
        ZoneClassification.pipeline_run_id == pipeline_run_id,
        ZoneClassification.zone_id == zone_id,
    ).first()

    if not cls:
        return 0.0

    avg_congestion = cls.avg_abs_congestion or 0.0
    congested_pct = cls.congested_hours_pct or 0.0
    congested_hours = congested_pct * HOURS_PER_YEAR

    value = avg_congestion * congested_hours * coincidence_factor * capacity_mw
    return round(value, 2)


def _compute_pnode_multiplier(
    db: Session,
    pipeline_run_id: int,
    zone_id: Optional[int],
    pnode_id: Optional[int],
) -> float:
    """
    Pnode-level multiplier: location premium/discount vs zone mean severity.

    Formula: 1.0 + (pnode_severity - zone_mean_severity)
    Range: typically 0.5 to 2.0
    """
    if not pnode_id or not zone_id:
        return 1.0

    # Get pnode severity
    pnode_score = db.query(PnodeScore).filter(
        PnodeScore.pipeline_run_id == pipeline_run_id,
        PnodeScore.pnode_id == pnode_id,
    ).first()

    if not pnode_score:
        return 1.0

    # Get zone mean severity
    from sqlalchemy import func
    zone_avg = (
        db.query(func.avg(PnodeScore.severity_score))
        .join(Pnode)
        .filter(
            PnodeScore.pipeline_run_id == pipeline_run_id,
            Pnode.zone_id == zone_id,
        )
        .scalar()
    )

    if zone_avg is None or zone_avg < 1e-6:
        return 1.0

    multiplier = 1.0 + (pnode_score.severity_score - zone_avg)
    # Clamp to reasonable range
    return round(max(0.3, min(3.0, multiplier)), 4)


def _compute_substation_value(
    db: Session,
    substation_id: Optional[int],
    coincidence_factor: float,
    capacity_mw: float,
    config: dict,
) -> float:
    """
    Substation loading value: relief from deferring capacity upgrades.

    Formula: loading_relief * peak_loading_pct * avoided_capacity_cost * capacity_mw
    Only applies when substation is loaded above 80%.
    """
    if not substation_id:
        return 0.0

    sub = db.query(Substation).get(substation_id)
    if not sub or not sub.peak_loading_pct:
        return 0.0

    loading_pct = sub.peak_loading_pct / 100.0 if sub.peak_loading_pct > 1.0 else sub.peak_loading_pct

    # Only value loading relief above 80% threshold
    if loading_pct < 0.80:
        return 0.0

    # Loading relief factor: how much the DER alleviates the overload
    # Scales linearly from 80% to 120%+
    loading_factor = min(1.0, (loading_pct - 0.80) / 0.40)

    avoided_cost = config.get("avoided_capacity_cost", DEFAULT_AVOIDED_CAPACITY_COST)

    # Value = loading_factor * coincidence * capacity_kw * avoided_cost_per_kw
    capacity_kw = capacity_mw * 1000
    value = loading_factor * coincidence_factor * capacity_kw * avoided_cost
    return round(value, 2)


def _compute_feeder_value(
    db: Session,
    feeder_id: Optional[int],
    coincidence_factor: float,
    capacity_mw: float,
    config: dict,
) -> float:
    """
    Feeder capacity value: relief from deferring feeder upgrades.

    Same pattern as substation but with feeder-level loading data.
    Returns 0 if no feeder data available (Phase 2 enhancement).
    """
    if not feeder_id:
        return 0.0

    feeder = db.query(Feeder).get(feeder_id)
    if not feeder or not feeder.peak_loading_pct:
        return 0.0

    loading_pct = feeder.peak_loading_pct / 100.0 if feeder.peak_loading_pct > 1.0 else feeder.peak_loading_pct

    if loading_pct < 0.80:
        return 0.0

    loading_factor = min(1.0, (loading_pct - 0.80) / 0.40)
    avoided_cost = config.get("avoided_feeder_cost", DEFAULT_AVOIDED_FEEDER_COST)

    capacity_kw = capacity_mw * 1000
    value = loading_factor * coincidence_factor * capacity_kw * avoided_cost
    return round(value, 2)


def _assign_value_tier(value_per_kw_year: float, thresholds: dict) -> str:
    """Assign value tier based on $/kW-year thresholds."""
    if value_per_kw_year >= thresholds.get("premium", 150.0):
        return "premium"
    elif value_per_kw_year >= thresholds.get("high", 80.0):
        return "high"
    elif value_per_kw_year >= thresholds.get("moderate", 30.0):
        return "moderate"
    return "low"
