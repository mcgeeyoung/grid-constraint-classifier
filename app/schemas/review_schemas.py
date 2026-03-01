"""Pydantic schemas for the extraction review queue API."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class ExtractionReviewResponse(BaseModel):
    """Review queue item (list view)."""
    id: int
    extraction_type: str
    confidence: str
    review_status: str
    source_file: Optional[str] = None
    llm_model: Optional[str] = None
    utility_name: Optional[str] = None
    docket_number: Optional[str] = None
    record_count: int = 0
    created_at: Optional[datetime] = None
    reviewed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ExtractionReviewDetail(BaseModel):
    """Full review item with extracted data and provenance."""
    id: int
    extraction_type: str
    extracted_data: dict
    confidence: str
    review_status: str
    source_file: Optional[str] = None
    raw_text_snippet: Optional[str] = None
    source_page: Optional[int] = None
    llm_model: Optional[str] = None
    extraction_notes: Optional[str] = None
    reviewer_notes: Optional[str] = None
    promoted_count: Optional[int] = None
    utility_id: Optional[int] = None
    utility_name: Optional[str] = None
    filing_id: Optional[int] = None
    docket_number: Optional[str] = None
    created_at: Optional[datetime] = None
    reviewed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ReviewAction(BaseModel):
    """Request body for approve/reject actions."""
    reviewer_notes: Optional[str] = None


class ReviewEdit(BaseModel):
    """Request body for editing extracted data before approval."""
    extracted_data: dict
    reviewer_notes: Optional[str] = None


class ReviewQueueStats(BaseModel):
    """Summary statistics for the review queue."""
    total: int
    pending: int
    approved: int
    rejected: int
    edited: int
    by_type: dict[str, int]
    by_confidence: dict[str, int]
