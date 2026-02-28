"""Partition zone_lmps table by iso_id using PostgreSQL list partitioning.

Converts the monolithic zone_lmps table into a partitioned table with
one partition per ISO for improved query performance on large time-series data.
Also creates a materialized view for pre-computed hourly aggregations.

Revision ID: h0c3d7e81f9a
Revises: g9b2c6d70e8f
Create Date: 2026-02-28
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic
revision = "h0c3d7e81f9a"
down_revision = "g9b2c6d70e8f"
branch_labels = None
depends_on = None

# Known ISOs (iso_code -> expected iso.id)
# We create partitions for IDs 1-10 to cover current and near-future ISOs
PARTITION_IDS = list(range(1, 11))


def upgrade():
    # -- Step 1: Rename existing table to a temp name --
    op.execute("ALTER TABLE zone_lmps RENAME TO zone_lmps_old")

    # -- Step 2: Create partitioned parent table --
    op.execute("""
        CREATE TABLE zone_lmps (
            id SERIAL,
            iso_id INTEGER NOT NULL REFERENCES isos(id),
            zone_id INTEGER NOT NULL REFERENCES zones(id),
            timestamp_utc TIMESTAMPTZ NOT NULL,
            lmp DOUBLE PRECISION NOT NULL,
            energy DOUBLE PRECISION,
            congestion DOUBLE PRECISION,
            loss DOUBLE PRECISION,
            hour_local SMALLINT NOT NULL,
            month SMALLINT NOT NULL,
            PRIMARY KEY (id, iso_id)
        ) PARTITION BY LIST (iso_id)
    """)

    # -- Step 3: Create partitions for each ISO --
    for iso_id in PARTITION_IDS:
        op.execute(f"""
            CREATE TABLE zone_lmps_iso_{iso_id}
            PARTITION OF zone_lmps
            FOR VALUES IN ({iso_id})
        """)

    # Default partition for any unexpected iso_id values
    op.execute("""
        CREATE TABLE zone_lmps_default
        PARTITION OF zone_lmps
        DEFAULT
    """)

    # -- Step 4: Copy data from old table to partitioned table --
    op.execute("""
        INSERT INTO zone_lmps (id, iso_id, zone_id, timestamp_utc, lmp, energy,
                                congestion, loss, hour_local, month)
        SELECT id, iso_id, zone_id, timestamp_utc, lmp, energy,
               congestion, loss, hour_local, month
        FROM zone_lmps_old
    """)

    # -- Step 5: Reset the sequence to continue from max id --
    op.execute("""
        SELECT setval('zone_lmps_id_seq',
                       COALESCE((SELECT MAX(id) FROM zone_lmps), 0) + 1,
                       false)
    """)

    # -- Step 6: Recreate indexes on partitioned table --
    # These will be automatically created on each partition
    op.execute(
        "CREATE INDEX ix_zone_lmps_iso_id ON zone_lmps (iso_id)"
    )
    op.execute(
        "CREATE INDEX ix_zone_lmps_zone_id ON zone_lmps (zone_id)"
    )
    op.execute(
        "CREATE INDEX ix_zone_lmps_timestamp_utc ON zone_lmps (timestamp_utc)"
    )
    op.execute(
        "CREATE INDEX ix_zone_lmps_iso_zone_ts ON zone_lmps (iso_id, zone_id, timestamp_utc)"
    )
    op.execute(
        "CREATE INDEX ix_zone_lmps_hour_local ON zone_lmps (hour_local)"
    )
    op.execute(
        "CREATE INDEX ix_zone_lmps_month ON zone_lmps (month)"
    )
    op.execute("""
        ALTER TABLE zone_lmps
        ADD CONSTRAINT uq_zone_lmps UNIQUE (iso_id, zone_id, timestamp_utc)
    """)

    # -- Step 7: Drop old table --
    op.execute("DROP TABLE zone_lmps_old")

    # -- Step 8: Create materialized view for hourly aggregations --
    op.execute("""
        CREATE MATERIALIZED VIEW zone_lmp_hourly_avg AS
        SELECT
            iso_id,
            zone_id,
            hour_local,
            month,
            AVG(congestion) AS avg_congestion,
            AVG(ABS(congestion)) AS avg_abs_congestion,
            MAX(ABS(congestion)) AS max_congestion,
            COUNT(*) AS sample_count
        FROM zone_lmps
        WHERE congestion IS NOT NULL
        GROUP BY iso_id, zone_id, hour_local, month
        WITH DATA
    """)

    # Indexes on the materialized view for fast lookups
    op.execute("""
        CREATE UNIQUE INDEX ix_zlha_iso_zone_hour_month
        ON zone_lmp_hourly_avg (iso_id, zone_id, hour_local, month)
    """)
    op.execute("""
        CREATE INDEX ix_zlha_iso_zone
        ON zone_lmp_hourly_avg (iso_id, zone_id)
    """)

    # Annual aggregation view (no month filter)
    op.execute("""
        CREATE MATERIALIZED VIEW zone_lmp_hourly_avg_annual AS
        SELECT
            iso_id,
            zone_id,
            hour_local,
            AVG(congestion) AS avg_congestion,
            AVG(ABS(congestion)) AS avg_abs_congestion,
            MAX(ABS(congestion)) AS max_congestion,
            COUNT(*) AS sample_count
        FROM zone_lmps
        WHERE congestion IS NOT NULL
        GROUP BY iso_id, zone_id, hour_local
        WITH DATA
    """)

    op.execute("""
        CREATE UNIQUE INDEX ix_zlhaa_iso_zone_hour
        ON zone_lmp_hourly_avg_annual (iso_id, zone_id, hour_local)
    """)
    op.execute("""
        CREATE INDEX ix_zlhaa_iso_zone
        ON zone_lmp_hourly_avg_annual (iso_id, zone_id)
    """)


def downgrade():
    # Drop materialized views
    op.execute("DROP MATERIALIZED VIEW IF EXISTS zone_lmp_hourly_avg_annual")
    op.execute("DROP MATERIALIZED VIEW IF EXISTS zone_lmp_hourly_avg")

    # Rename partitioned table
    op.execute("ALTER TABLE zone_lmps RENAME TO zone_lmps_partitioned")

    # Recreate original non-partitioned table
    op.execute("""
        CREATE TABLE zone_lmps (
            id SERIAL PRIMARY KEY,
            iso_id INTEGER NOT NULL REFERENCES isos(id),
            zone_id INTEGER NOT NULL REFERENCES zones(id),
            timestamp_utc TIMESTAMPTZ NOT NULL,
            lmp DOUBLE PRECISION NOT NULL,
            energy DOUBLE PRECISION,
            congestion DOUBLE PRECISION,
            loss DOUBLE PRECISION,
            hour_local SMALLINT NOT NULL,
            month SMALLINT NOT NULL,
            CONSTRAINT uq_zone_lmps UNIQUE (iso_id, zone_id, timestamp_utc)
        )
    """)

    # Copy data back
    op.execute("""
        INSERT INTO zone_lmps (id, iso_id, zone_id, timestamp_utc, lmp, energy,
                                congestion, loss, hour_local, month)
        SELECT id, iso_id, zone_id, timestamp_utc, lmp, energy,
               congestion, loss, hour_local, month
        FROM zone_lmps_partitioned
    """)

    op.execute("""
        SELECT setval('zone_lmps_id_seq',
                       COALESCE((SELECT MAX(id) FROM zone_lmps), 0) + 1,
                       false)
    """)

    # Recreate indexes
    op.execute("CREATE INDEX ix_zone_lmps_iso_id ON zone_lmps (iso_id)")
    op.execute("CREATE INDEX ix_zone_lmps_zone_id ON zone_lmps (zone_id)")
    op.execute("CREATE INDEX ix_zone_lmps_timestamp_utc ON zone_lmps (timestamp_utc)")
    op.execute(
        "CREATE INDEX ix_zone_lmps_iso_zone_ts ON zone_lmps (iso_id, zone_id, timestamp_utc)"
    )
    op.execute("CREATE INDEX ix_zone_lmps_hour_local ON zone_lmps (hour_local)")
    op.execute("CREATE INDEX ix_zone_lmps_month ON zone_lmps (month)")

    # Drop partitioned table and all partitions
    op.execute("DROP TABLE zone_lmps_partitioned")
