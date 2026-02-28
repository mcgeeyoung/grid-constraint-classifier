"""Materialized view refresh helpers.

Refreshes pre-computed aggregation views after pipeline data changes.
Called from pipeline_writer.complete_run() and can be triggered manually.
"""

import logging

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

MATERIALIZED_VIEWS = [
    "zone_lmp_hourly_avg",
    "zone_lmp_hourly_avg_annual",
]


def refresh_materialized_views(db: Session) -> None:
    """Refresh all LMP materialized views concurrently.

    Uses CONCURRENTLY to avoid locking reads during refresh.
    Falls back to non-concurrent refresh if the unique index is missing.
    """
    for view_name in MATERIALIZED_VIEWS:
        try:
            db.execute(text(f"REFRESH MATERIALIZED VIEW CONCURRENTLY {view_name}"))
            logger.info(f"Refreshed materialized view: {view_name}")
        except Exception:
            try:
                db.rollback()
                db.execute(text(f"REFRESH MATERIALIZED VIEW {view_name}"))
                db.commit()
                logger.info(f"Refreshed materialized view (non-concurrent): {view_name}")
            except Exception as e:
                logger.warning(f"Failed to refresh {view_name}: {e}")
                db.rollback()
