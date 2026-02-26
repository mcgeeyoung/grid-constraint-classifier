"""
Retrospective DER Valuation Engine.

Computes realized constraint-relief value using actual metered savings
from the WattCarbon API, applied through the same valuation framework
as the prospective engine.

Key difference from prospective: instead of nameplate_capacity * coincidence_factor,
we use the asset's actual metered output as the savings input.
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.models import (
    ZoneLMP, Substation, Feeder, Pnode,
    PnodeScore, PipelineRun, HierarchyScore,
    DERLocation,
)
from core.valuation_engine import (
    _compute_pnode_multiplier,
    DEFAULT_AVOIDED_CAPACITY_COST,
    DEFAULT_AVOIDED_FEEDER_COST,
)

logger = logging.getLogger(__name__)


@dataclass
class RetrospectiveResult:
    """Output of a retrospective valuation computation."""
    actual_savings_mwh: float = 0.0
    actual_constraint_relief_value: float = 0.0
    actual_zone_congestion_value: float = 0.0
    actual_substation_value: float = 0.0
    actual_feeder_value: float = 0.0
    retrospective_start: Optional[datetime] = None
    retrospective_end: Optional[datetime] = None


def compute_retrospective_value(
    db: Session,
    wattcarbon_client,
    der_location: DERLocation,
    start: datetime,
    end: datetime,
    pipeline_run_id: Optional[int] = None,
) -> RetrospectiveResult:
    """
    Compute realized constraint-relief value from actual metered savings.

    Data flow:
    1. Pull hourly meter timeseries from WattCarbon
    2. Sum total savings (MWh)
    3. Compute zone congestion relief: actual savings * hourly congestion price
    4. Compute substation avoided cost: coincident peak savings * avoided $/kW-yr
    5. Compute feeder avoided cost: same pattern as substation

    Args:
        db: Database session
        wattcarbon_client: Authenticated WattCarbonClient instance
        der_location: DERLocation record with grid hierarchy resolved
        start: Retrospective period start
        end: Retrospective period end
        pipeline_run_id: Pipeline run for pnode multiplier lookup

    Returns:
        RetrospectiveResult with actual savings and value components.
    """
    result = RetrospectiveResult(
        retrospective_start=start,
        retrospective_end=end,
    )

    # Get meter ID from the WattCarbon asset
    asset_id = der_location.wattcarbon_asset_id
    if not asset_id:
        logger.warning(f"DERLocation {der_location.id} has no wattcarbon_asset_id")
        return result

    # Fetch asset details to find meter_id
    asset = wattcarbon_client.get_asset(asset_id)
    meter_id = asset.get("meter_id") or asset.get("meterId")
    if not meter_id:
        # Try nested meters list
        meters = asset.get("meters", [])
        if meters:
            meter_id = meters[0].get("id") or meters[0].get("meter_id")

    if not meter_id:
        logger.warning(f"Asset {asset_id} has no associated meter")
        return result

    # Pull hourly timeseries
    intervals = wattcarbon_client.get_meter_timeseries(meter_id, start, end)
    if not intervals:
        logger.warning(f"No timeseries data for meter {meter_id}")
        return result

    # Parse intervals into hourly savings
    hourly_data = _parse_intervals(intervals)
    total_savings_mwh = sum(h["value_mwh"] for h in hourly_data)
    result.actual_savings_mwh = round(total_savings_mwh, 4)

    # Resolve pipeline run for multiplier lookups
    run_id = pipeline_run_id
    if not run_id and der_location.iso_id:
        run = (
            db.query(PipelineRun)
            .filter(
                PipelineRun.iso_id == der_location.iso_id,
                PipelineRun.status == "completed",
            )
            .order_by(PipelineRun.completed_at.desc())
            .first()
        )
        if run:
            run_id = run.id

    # 1. Zone congestion relief: sum(hourly_savings * hourly_congestion_price)
    zone_congestion = _compute_zone_congestion_from_timeseries(
        db, der_location.zone_id, hourly_data,
    )

    # Apply pnode multiplier
    pnode_mult = 1.0
    if run_id:
        pnode_mult = _compute_pnode_multiplier(
            db, run_id, der_location.zone_id, der_location.nearest_pnode_id,
        )

    result.actual_zone_congestion_value = round(zone_congestion * pnode_mult, 2)

    # 2. Substation avoided cost: peak coincident savings * loading factor * avoided cost
    sub_value = _compute_sub_retro(
        db, der_location.substation_id, hourly_data,
        pipeline_run_id=run_id,
    )
    result.actual_substation_value = sub_value

    # 3. Feeder avoided cost
    feeder_value = _compute_feeder_retro(
        db, der_location.feeder_id, hourly_data,
        pipeline_run_id=run_id,
    )
    result.actual_feeder_value = feeder_value

    # 4. Total
    result.actual_constraint_relief_value = round(
        result.actual_zone_congestion_value
        + result.actual_substation_value
        + result.actual_feeder_value,
        2,
    )

    logger.info(
        f"Retrospective valuation for DER {der_location.id}: "
        f"{result.actual_savings_mwh:.2f} MWh savings, "
        f"${result.actual_constraint_relief_value:.2f} total value"
    )

    return result


def _parse_intervals(intervals: list[dict]) -> list[dict]:
    """Parse WattCarbon timeseries intervals into normalized hourly records.

    Each record: {"timestamp": datetime, "value_mwh": float, "month": int, "hour": int}
    """
    parsed = []
    for iv in intervals:
        ts_str = iv.get("timestamp") or iv.get("datetime") or iv.get("start")
        value = iv.get("value_mwh") or iv.get("value") or iv.get("kwh", 0) / 1000.0

        if ts_str is None:
            continue

        if isinstance(ts_str, str):
            # Handle ISO format timestamps
            ts_str = ts_str.replace("Z", "+00:00")
            try:
                ts = datetime.fromisoformat(ts_str)
            except ValueError:
                continue
        elif isinstance(ts_str, datetime):
            ts = ts_str
        else:
            continue

        parsed.append({
            "timestamp": ts,
            "value_mwh": float(value) if value else 0.0,
            "month": ts.month,
            "hour": ts.hour,
        })

    return parsed


def _compute_zone_congestion_from_timeseries(
    db: Session,
    zone_id: Optional[int],
    hourly_data: list[dict],
) -> float:
    """Compute zone congestion relief from actual hourly savings.

    For each hour: savings_mwh * congestion_$/MWh from ZoneLMP.
    """
    if not zone_id or not hourly_data:
        return 0.0

    # Build a lookup of average congestion by (month, hour) from ZoneLMP
    lmps = (
        db.query(ZoneLMP)
        .filter(ZoneLMP.zone_id == zone_id)
        .all()
    )

    if not lmps:
        return 0.0

    # Average congestion by (month, hour_local)
    congestion_map: dict[tuple[int, int], list[float]] = {}
    for lmp in lmps:
        key = (lmp.month, lmp.hour_local)
        if lmp.congestion is not None:
            congestion_map.setdefault(key, []).append(abs(lmp.congestion))

    avg_congestion: dict[tuple[int, int], float] = {}
    for key, values in congestion_map.items():
        avg_congestion[key] = sum(values) / len(values)

    # Sum hourly zone value
    total = 0.0
    for h in hourly_data:
        key = (h["month"], h["hour"])
        cong_price = avg_congestion.get(key, 0.0)
        total += h["value_mwh"] * cong_price

    return total


def _compute_sub_retro(
    db: Session,
    substation_id: Optional[int],
    hourly_data: list[dict],
    pipeline_run_id: Optional[int] = None,
) -> float:
    """Retrospective substation avoided cost from actual peak savings."""
    if not substation_id or not hourly_data:
        return 0.0

    sub = db.query(Substation).get(substation_id)
    if not sub or not sub.peak_loading_pct:
        return 0.0

    loading_pct = sub.peak_loading_pct / 100.0 if sub.peak_loading_pct > 1.0 else sub.peak_loading_pct
    if loading_pct < 0.80:
        return 0.0

    loading_factor = min(1.0, (loading_pct - 0.80) / 0.40)

    # Peak coincident savings: max hourly savings (kW)
    peak_savings_mwh = max(h["value_mwh"] for h in hourly_data) if hourly_data else 0.0
    peak_savings_kw = peak_savings_mwh * 1000.0  # MWh in 1 hour = MW = 1000 kW

    value = loading_factor * peak_savings_kw * DEFAULT_AVOIDED_CAPACITY_COST

    # Hierarchy score boost
    if pipeline_run_id:
        h_score = (
            db.query(HierarchyScore)
            .filter(
                HierarchyScore.pipeline_run_id == pipeline_run_id,
                HierarchyScore.level == "substation",
                HierarchyScore.entity_id == substation_id,
            )
            .first()
        )
        if h_score and h_score.combined_score:
            value *= 1.0 + 0.5 * h_score.combined_score

    return round(value, 2)


def _compute_feeder_retro(
    db: Session,
    feeder_id: Optional[int],
    hourly_data: list[dict],
    pipeline_run_id: Optional[int] = None,
) -> float:
    """Retrospective feeder avoided cost from actual peak savings."""
    if not feeder_id or not hourly_data:
        return 0.0

    feeder = db.query(Feeder).get(feeder_id)
    if not feeder or not feeder.peak_loading_pct:
        return 0.0

    loading_pct = feeder.peak_loading_pct / 100.0 if feeder.peak_loading_pct > 1.0 else feeder.peak_loading_pct
    if loading_pct < 0.80:
        return 0.0

    loading_factor = min(1.0, (loading_pct - 0.80) / 0.40)

    peak_savings_mwh = max(h["value_mwh"] for h in hourly_data) if hourly_data else 0.0
    peak_savings_kw = peak_savings_mwh * 1000.0

    value = loading_factor * peak_savings_kw * DEFAULT_AVOIDED_FEEDER_COST

    if pipeline_run_id:
        h_score = (
            db.query(HierarchyScore)
            .filter(
                HierarchyScore.pipeline_run_id == pipeline_run_id,
                HierarchyScore.level == "feeder",
                HierarchyScore.entity_id == feeder_id,
            )
            .first()
        )
        if h_score and h_score.combined_score:
            value *= 1.0 + 0.5 * h_score.combined_score

    return round(value, 2)
