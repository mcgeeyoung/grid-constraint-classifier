"""
Hierarchy scorer: computes pre-aggregated constraint scores at each
level of the grid hierarchy (zone, substation, feeder) during pipeline runs.

Scores are stored in the hierarchy_scores table and used by the valuation
engine and browsing API to quickly rank constrained locations.
"""

import logging
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import (
    Zone, ZoneClassification, Substation, Feeder,
    Pnode, PnodeScore, HierarchyScore,
)

logger = logging.getLogger(__name__)

# Weights for combining congestion (TX) and loading (DX) scores
TX_WEIGHT = 0.5
DX_WEIGHT = 0.5


def _risk_label(congestion_score: float, loading_score: float) -> str:
    """
    Assign constraint tier based on congestion and loading scores.

    Reuses the same threshold pattern as src/grip_overlay.py:_risk_label().
    """
    if congestion_score >= 0.5 and loading_score >= 0.5:
        return "CRITICAL"
    elif congestion_score >= 0.5 or loading_score >= 0.5:
        return "ELEVATED"
    elif congestion_score >= 0.25 or loading_score >= 0.25:
        return "MODERATE"
    return "LOW"


def compute_zone_scores(
    db: Session,
    pipeline_run_id: int,
    iso_id: int,
) -> list[dict]:
    """
    Compute hierarchy scores at the zone level.

    congestion_score: from ZoneClassification.transmission_score (already 0-1)
    loading_score: average substation peak_loading_pct in zone, normalized to 0-1
    """
    classifications = (
        db.query(ZoneClassification)
        .filter(ZoneClassification.pipeline_run_id == pipeline_run_id)
        .all()
    )

    if not classifications:
        return []

    # Get avg substation loading per zone
    zone_loading = dict(
        db.query(
            Substation.zone_id,
            func.avg(Substation.peak_loading_pct),
        )
        .filter(
            Substation.iso_id == iso_id,
            Substation.zone_id.isnot(None),
            Substation.peak_loading_pct.isnot(None),
        )
        .group_by(Substation.zone_id)
        .all()
    )

    scores = []
    for cls in classifications:
        congestion = cls.transmission_score or 0.0
        # Clamp to 0-1
        congestion = max(0.0, min(1.0, congestion))

        avg_loading = zone_loading.get(cls.zone_id, 0.0) or 0.0
        # Normalize loading: 0% -> 0.0, 100%+ -> 1.0
        loading = max(0.0, min(1.0, avg_loading / 100.0))

        combined = TX_WEIGHT * congestion + DX_WEIGHT * loading
        tier = _risk_label(congestion, loading)

        scores.append({
            "level": "zone",
            "entity_id": cls.zone_id,
            "congestion_score": round(congestion, 4),
            "loading_score": round(loading, 4),
            "combined_score": round(combined, 4),
            "constraint_tier": tier,
        })

    logger.info(f"Hierarchy: Computed {len(scores)} zone scores")
    return scores


def compute_substation_scores(
    db: Session,
    pipeline_run_id: int,
    iso_id: int,
) -> list[dict]:
    """
    Compute hierarchy scores at the substation level.

    congestion_score: severity_score of the nearest pnode, normalized to 0-1
    loading_score: peak_loading_pct / 100, clamped to 0-1
    """
    substations = (
        db.query(Substation)
        .filter(
            Substation.iso_id == iso_id,
            Substation.lat.isnot(None),
        )
        .all()
    )

    if not substations:
        return []

    # Build pnode severity lookup for this pipeline run
    pnode_severity = dict(
        db.query(PnodeScore.pnode_id, PnodeScore.severity_score)
        .filter(PnodeScore.pipeline_run_id == pipeline_run_id)
        .all()
    )

    # Get max severity for normalization
    max_severity = max(pnode_severity.values()) if pnode_severity else 1.0
    if max_severity < 1e-6:
        max_severity = 1.0

    scores = []
    for sub in substations:
        # Congestion: from nearest pnode severity
        raw_severity = pnode_severity.get(sub.nearest_pnode_id, 0.0)
        congestion = max(0.0, min(1.0, raw_severity / max_severity))

        # Loading: from peak loading percentage
        loading_pct = sub.peak_loading_pct or 0.0
        loading = max(0.0, min(1.0, loading_pct / 100.0))

        combined = TX_WEIGHT * congestion + DX_WEIGHT * loading
        tier = _risk_label(congestion, loading)

        scores.append({
            "level": "substation",
            "entity_id": sub.id,
            "congestion_score": round(congestion, 4),
            "loading_score": round(loading, 4),
            "combined_score": round(combined, 4),
            "constraint_tier": tier,
        })

    logger.info(f"Hierarchy: Computed {len(scores)} substation scores")
    return scores


def compute_feeder_scores(
    db: Session,
    pipeline_run_id: int,
    iso_id: int,
) -> list[dict]:
    """
    Compute hierarchy scores at the feeder level.

    congestion_score: inherited from parent substation's nearest pnode severity
    loading_score: feeder peak_loading_pct / 100, clamped to 0-1
    """
    feeders = (
        db.query(Feeder, Substation)
        .join(Substation, Feeder.substation_id == Substation.id)
        .filter(Substation.iso_id == iso_id)
        .all()
    )

    if not feeders:
        return []

    # Build pnode severity lookup
    pnode_severity = dict(
        db.query(PnodeScore.pnode_id, PnodeScore.severity_score)
        .filter(PnodeScore.pipeline_run_id == pipeline_run_id)
        .all()
    )

    max_severity = max(pnode_severity.values()) if pnode_severity else 1.0
    if max_severity < 1e-6:
        max_severity = 1.0

    scores = []
    for feeder, sub in feeders:
        # Congestion: inherited from parent substation
        raw_severity = pnode_severity.get(sub.nearest_pnode_id, 0.0)
        congestion = max(0.0, min(1.0, raw_severity / max_severity))

        # Loading: from feeder peak loading
        loading_pct = feeder.peak_loading_pct or 0.0
        loading = max(0.0, min(1.0, loading_pct / 100.0))

        combined = TX_WEIGHT * congestion + DX_WEIGHT * loading
        tier = _risk_label(congestion, loading)

        scores.append({
            "level": "feeder",
            "entity_id": feeder.id,
            "congestion_score": round(congestion, 4),
            "loading_score": round(loading, 4),
            "combined_score": round(combined, 4),
            "constraint_tier": tier,
        })

    if scores:
        logger.info(f"Hierarchy: Computed {len(scores)} feeder scores")
    return scores


def compute_all_hierarchy_scores(
    db: Session,
    pipeline_run_id: int,
    iso_id: int,
) -> list[dict]:
    """
    Compute hierarchy scores at all levels (zone, substation, feeder).

    Returns a flat list of score dicts ready for write_hierarchy_scores().
    """
    all_scores = []
    all_scores.extend(compute_zone_scores(db, pipeline_run_id, iso_id))
    all_scores.extend(compute_substation_scores(db, pipeline_run_id, iso_id))
    all_scores.extend(compute_feeder_scores(db, pipeline_run_id, iso_id))

    tier_counts = {}
    for s in all_scores:
        tier_counts[s["constraint_tier"]] = tier_counts.get(s["constraint_tier"], 0) + 1

    logger.info(
        f"Hierarchy: {len(all_scores)} total scores | "
        f"CRITICAL={tier_counts.get('CRITICAL', 0)} "
        f"ELEVATED={tier_counts.get('ELEVATED', 0)} "
        f"MODERATE={tier_counts.get('MODERATE', 0)} "
        f"LOW={tier_counts.get('LOW', 0)}"
    )

    return all_scores
