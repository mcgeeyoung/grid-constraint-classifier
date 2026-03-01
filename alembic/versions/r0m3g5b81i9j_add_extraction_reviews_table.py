"""Add extraction_reviews table for human-in-the-loop review queue.

Revision ID: r0m3g5b81i9j
Revises: q9l2f4a70h8i
Create Date: 2026-02-28
"""

from alembic import op
import sqlalchemy as sa

revision = "r0m3g5b81i9j"
down_revision = "q9l2f4a70h8i"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "extraction_reviews",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("utility_id", sa.Integer, sa.ForeignKey("utilities.id"), nullable=True),
        sa.Column("filing_id", sa.Integer, sa.ForeignKey("filings.id"), nullable=True),
        sa.Column("filing_document_id", sa.Integer, sa.ForeignKey("filing_documents.id"), nullable=True),
        sa.Column("extraction_type", sa.String(50), nullable=False),
        sa.Column("extracted_data", sa.JSON, nullable=False),
        sa.Column("confidence", sa.String(20), nullable=False),
        sa.Column("source_file", sa.String(500), nullable=True),
        sa.Column("raw_text_snippet", sa.Text, nullable=True),
        sa.Column("source_page", sa.Integer, nullable=True),
        sa.Column("llm_model", sa.String(100), nullable=True),
        sa.Column("extraction_notes", sa.Text, nullable=True),
        sa.Column("review_status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("reviewer_notes", sa.Text, nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("promoted_count", sa.Integer, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_index("ix_er_status", "extraction_reviews", ["review_status"])
    op.create_index("ix_er_type", "extraction_reviews", ["extraction_type"])
    op.create_index("ix_er_confidence", "extraction_reviews", ["confidence"])
    op.create_index("ix_er_utility", "extraction_reviews", ["utility_id"])
    op.create_index("ix_er_filing", "extraction_reviews", ["filing_id"])


def downgrade() -> None:
    op.drop_index("ix_er_filing", "extraction_reviews")
    op.drop_index("ix_er_utility", "extraction_reviews")
    op.drop_index("ix_er_confidence", "extraction_reviews")
    op.drop_index("ix_er_type", "extraction_reviews")
    op.drop_index("ix_er_status", "extraction_reviews")
    op.drop_table("extraction_reviews")
