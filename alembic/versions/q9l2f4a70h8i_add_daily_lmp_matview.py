"""Add zone_lmp_daily_avg materialized view for time-series display.

Revision ID: q9l2f4a70h8i
Revises: p8k1e3f69g7h
Create Date: 2026-02-28
"""

from alembic import op

# revision identifiers, used by Alembic
revision = "q9l2f4a70h8i"
down_revision = "p8k1e3f69g7h"
branch_labels = None
depends_on = None


def upgrade():
    # Daily rollup materialized view for multi-month/year time-series charts
    op.execute("""
        CREATE MATERIALIZED VIEW zone_lmp_daily_avg AS
        SELECT
            iso_id,
            zone_id,
            DATE(timestamp_utc AT TIME ZONE 'UTC') AS day,
            AVG(lmp) AS avg_lmp,
            AVG(congestion) AS avg_congestion,
            AVG(energy) AS avg_energy,
            AVG(loss) AS avg_loss,
            MAX(congestion) AS max_congestion,
            MIN(congestion) AS min_congestion,
            COUNT(*) AS sample_count
        FROM zone_lmps
        GROUP BY iso_id, zone_id, DATE(timestamp_utc AT TIME ZONE 'UTC')
        WITH DATA
    """)

    # Unique index required for CONCURRENTLY refresh
    op.execute("""
        CREATE UNIQUE INDEX ix_zlda_iso_zone_day
        ON zone_lmp_daily_avg (iso_id, zone_id, day)
    """)
    op.execute("""
        CREATE INDEX ix_zlda_iso_zone
        ON zone_lmp_daily_avg (iso_id, zone_id)
    """)
    op.execute("""
        CREATE INDEX ix_zlda_day
        ON zone_lmp_daily_avg (day)
    """)


def downgrade():
    op.execute("DROP MATERIALIZED VIEW IF EXISTS zone_lmp_daily_avg")
