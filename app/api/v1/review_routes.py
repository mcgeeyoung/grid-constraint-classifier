"""API v1 routes for the extraction review queue (human-in-the-loop)."""

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import (
    ExtractionReview, Utility, Filing,
    GridConstraint, LoadForecast, ResourceNeed,
)
from app.schemas.review_schemas import (
    ExtractionReviewResponse,
    ExtractionReviewDetail,
    ReviewAction,
    ReviewEdit,
    ReviewQueueStats,
)

router = APIRouter(prefix="/api/v1/review")


# ------------------------------------------------------------------
# Queue listing + stats
# ------------------------------------------------------------------

@router.get("/queue", response_model=list[ExtractionReviewResponse])
def list_review_queue(
    status: Optional[str] = Query(default="pending"),
    extraction_type: Optional[str] = Query(default=None),
    confidence: Optional[str] = Query(default=None),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    """List review queue items with optional filters."""
    query = db.query(ExtractionReview)

    if status:
        query = query.filter(ExtractionReview.review_status == status)
    if extraction_type:
        query = query.filter(ExtractionReview.extraction_type == extraction_type)
    if confidence:
        query = query.filter(ExtractionReview.confidence == confidence)

    items = (
        query
        .order_by(ExtractionReview.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    results = []
    for item in items:
        utility_name = None
        docket_number = None
        if item.utility_id:
            util = db.query(Utility.utility_name).filter(Utility.id == item.utility_id).first()
            utility_name = util[0] if util else None
        if item.filing_id:
            filing = db.query(Filing.docket_number).filter(Filing.id == item.filing_id).first()
            docket_number = filing[0] if filing else None

        record_count = _count_records(item.extracted_data, item.extraction_type)

        results.append(ExtractionReviewResponse(
            id=item.id,
            extraction_type=item.extraction_type,
            confidence=item.confidence,
            review_status=item.review_status,
            source_file=item.source_file,
            llm_model=item.llm_model,
            utility_name=utility_name,
            docket_number=docket_number,
            record_count=record_count,
            created_at=item.created_at,
            reviewed_at=item.reviewed_at,
        ))

    return results


@router.get("/stats", response_model=ReviewQueueStats)
def review_queue_stats(db: Session = Depends(get_db)):
    """Get summary statistics for the review queue."""
    total = db.query(func.count(ExtractionReview.id)).scalar() or 0

    status_counts = dict(
        db.query(ExtractionReview.review_status, func.count(ExtractionReview.id))
        .group_by(ExtractionReview.review_status)
        .all()
    )

    type_counts = dict(
        db.query(ExtractionReview.extraction_type, func.count(ExtractionReview.id))
        .group_by(ExtractionReview.extraction_type)
        .all()
    )

    confidence_counts = dict(
        db.query(ExtractionReview.confidence, func.count(ExtractionReview.id))
        .group_by(ExtractionReview.confidence)
        .all()
    )

    return ReviewQueueStats(
        total=total,
        pending=status_counts.get("pending", 0),
        approved=status_counts.get("approved", 0),
        rejected=status_counts.get("rejected", 0),
        edited=status_counts.get("edited", 0),
        by_type=type_counts,
        by_confidence=confidence_counts,
    )


# ------------------------------------------------------------------
# Single item detail
# ------------------------------------------------------------------

@router.get("/queue/{item_id}", response_model=ExtractionReviewDetail)
def get_review_item(item_id: int, db: Session = Depends(get_db)):
    """Get full detail for a single review queue item."""
    item = db.query(ExtractionReview).filter(ExtractionReview.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Review item not found")

    utility_name = None
    docket_number = None
    if item.utility_id:
        util = db.query(Utility.utility_name).filter(Utility.id == item.utility_id).first()
        utility_name = util[0] if util else None
    if item.filing_id:
        filing = db.query(Filing.docket_number).filter(Filing.id == item.filing_id).first()
        docket_number = filing[0] if filing else None

    return ExtractionReviewDetail(
        id=item.id,
        extraction_type=item.extraction_type,
        extracted_data=item.extracted_data,
        confidence=item.confidence,
        review_status=item.review_status,
        source_file=item.source_file,
        raw_text_snippet=item.raw_text_snippet,
        source_page=item.source_page,
        llm_model=item.llm_model,
        extraction_notes=item.extraction_notes,
        reviewer_notes=item.reviewer_notes,
        promoted_count=item.promoted_count,
        utility_id=item.utility_id,
        utility_name=utility_name,
        filing_id=item.filing_id,
        docket_number=docket_number,
        created_at=item.created_at,
        reviewed_at=item.reviewed_at,
    )


# ------------------------------------------------------------------
# Review actions
# ------------------------------------------------------------------

@router.post("/queue/{item_id}/approve", response_model=ExtractionReviewDetail)
def approve_item(
    item_id: int,
    body: ReviewAction = ReviewAction(),
    db: Session = Depends(get_db),
):
    """Approve an extraction and promote records to production tables."""
    item = db.query(ExtractionReview).filter(ExtractionReview.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Review item not found")
    if item.review_status != "pending":
        raise HTTPException(status_code=400, detail=f"Item already {item.review_status}")

    # Promote to production tables
    count = _promote_extraction(db, item)

    item.review_status = "approved"
    item.reviewer_notes = body.reviewer_notes
    item.reviewed_at = datetime.now(timezone.utc)
    item.promoted_count = count
    db.commit()
    db.refresh(item)

    return _build_detail(db, item)


@router.post("/queue/{item_id}/reject", response_model=ExtractionReviewDetail)
def reject_item(
    item_id: int,
    body: ReviewAction = ReviewAction(),
    db: Session = Depends(get_db),
):
    """Reject an extraction (no records promoted)."""
    item = db.query(ExtractionReview).filter(ExtractionReview.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Review item not found")
    if item.review_status != "pending":
        raise HTTPException(status_code=400, detail=f"Item already {item.review_status}")

    item.review_status = "rejected"
    item.reviewer_notes = body.reviewer_notes
    item.reviewed_at = datetime.now(timezone.utc)
    item.promoted_count = 0
    db.commit()
    db.refresh(item)

    return _build_detail(db, item)


@router.put("/queue/{item_id}", response_model=ExtractionReviewDetail)
def edit_and_approve(
    item_id: int,
    body: ReviewEdit,
    db: Session = Depends(get_db),
):
    """Edit extracted data and approve (promote corrected records)."""
    item = db.query(ExtractionReview).filter(ExtractionReview.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Review item not found")
    if item.review_status not in ("pending", "rejected"):
        raise HTTPException(status_code=400, detail=f"Item already {item.review_status}")

    item.extracted_data = body.extracted_data
    count = _promote_extraction(db, item)

    item.review_status = "edited"
    item.reviewer_notes = body.reviewer_notes
    item.reviewed_at = datetime.now(timezone.utc)
    item.promoted_count = count
    db.commit()
    db.refresh(item)

    return _build_detail(db, item)


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _count_records(data: dict, extraction_type: str) -> int:
    """Count the number of individual records in an extraction."""
    if extraction_type == "load_forecast":
        return sum(len(s.get("data", [])) for s in data.get("scenarios", []))
    if extraction_type == "grid_constraint":
        return len(data.get("constraints", []))
    if extraction_type == "resource_need":
        return len(data.get("needs", []))
    if extraction_type == "hosting_capacity":
        return len(data.get("records", []))
    return 0


def _promote_extraction(db: Session, item: ExtractionReview) -> int:
    """Promote extraction data to production tables. Returns record count."""
    data = item.extracted_data
    utility_id = item.utility_id
    filing_id = item.filing_id
    count = 0

    if not utility_id:
        return 0

    if item.extraction_type == "load_forecast":
        for scenario in data.get("scenarios", []):
            for dp in scenario.get("data", []):
                lf = LoadForecast(
                    utility_id=utility_id,
                    filing_id=filing_id,
                    forecast_year=dp.get("year", 0),
                    area_name=data.get("area_name"),
                    area_type=data.get("area_type"),
                    peak_demand_mw=dp.get("peak_demand_mw"),
                    energy_gwh=dp.get("energy_gwh"),
                    growth_rate_pct=dp.get("growth_rate_pct"),
                    scenario=scenario.get("name"),
                )
                db.add(lf)
                count += 1

    elif item.extraction_type == "grid_constraint":
        for c in data.get("constraints", []):
            gc = GridConstraint(
                utility_id=utility_id,
                filing_id=filing_id,
                constraint_type=c.get("constraint_type", "unknown"),
                location_type=c.get("location_type"),
                location_name=c.get("location_name"),
                current_capacity_mw=c.get("current_capacity_mw"),
                forecasted_load_mw=c.get("forecasted_load_mw"),
                headroom_mw=c.get("headroom_mw"),
                constraint_year=c.get("constraint_year"),
                confidence="reviewed",
                notes=c.get("notes"),
                raw_source_reference=c.get("proposed_solution"),
            )
            db.add(gc)
            count += 1

    elif item.extraction_type == "resource_need":
        for n in data.get("needs", []):
            rn = ResourceNeed(
                utility_id=utility_id,
                filing_id=filing_id,
                need_type=n.get("need_type", "unknown"),
                need_mw=n.get("need_mw"),
                need_year=n.get("need_year"),
                location_type=n.get("location_type"),
                location_name=n.get("location_name"),
                eligible_resource_types=n.get("eligible_resource_types"),
                notes=n.get("notes"),
            )
            db.add(rn)
            count += 1

    return count


def _build_detail(db: Session, item: ExtractionReview) -> ExtractionReviewDetail:
    """Build detail response from an item."""
    utility_name = None
    docket_number = None
    if item.utility_id:
        util = db.query(Utility.utility_name).filter(Utility.id == item.utility_id).first()
        utility_name = util[0] if util else None
    if item.filing_id:
        filing = db.query(Filing.docket_number).filter(Filing.id == item.filing_id).first()
        docket_number = filing[0] if filing else None

    return ExtractionReviewDetail(
        id=item.id,
        extraction_type=item.extraction_type,
        extracted_data=item.extracted_data,
        confidence=item.confidence,
        review_status=item.review_status,
        source_file=item.source_file,
        raw_text_snippet=item.raw_text_snippet,
        source_page=item.source_page,
        llm_model=item.llm_model,
        extraction_notes=item.extraction_notes,
        reviewer_notes=item.reviewer_notes,
        promoted_count=item.promoted_count,
        utility_id=item.utility_id,
        utility_name=utility_name,
        filing_id=item.filing_id,
        docket_number=docket_number,
        created_at=item.created_at,
        reviewed_at=item.reviewed_at,
    )
