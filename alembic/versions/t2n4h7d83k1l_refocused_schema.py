"""Refocused architecture schema: constraint profiles, DER profiles, value stacks.

Merges BalancingAuthority into ISO table, creates 6 new tables:
- computation_runs (replaces pipeline_runs/hc_ingestion_runs)
- constraint_profiles (central 12x24 profiles)
- constraint_annotations (regulatory context)
- der_profiles (DER output patterns)
- constraint_der_intersections (profile x DER value)
- location_value_stacks (composite value)

Creates materialized views:
- mv_zone_constraint_summary
- mv_location_rankings

Revision ID: t2n4h7d83k1l
Revises: s1m3g6c92j0k
Create Date: 2026-03-02
"""

from alembic import op
import sqlalchemy as sa

revision = "t2n4h7d83k1l"
down_revision = "s1m3g6c92j0k"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ============================================================
    # Step 1: Add BA columns to isos table (13 new columns)
    # ============================================================
    op.add_column("isos", sa.Column("ba_code", sa.String(10), unique=True, nullable=True))
    op.add_column("isos", sa.Column("ba_name", sa.String(200), nullable=True))
    op.add_column("isos", sa.Column("is_rto", sa.Boolean(), server_default="false", nullable=False))
    op.add_column("isos", sa.Column("parent_iso_id", sa.Integer(), sa.ForeignKey("isos.id"), nullable=True))
    op.add_column("isos", sa.Column("region", sa.String(50), nullable=True))
    op.add_column("isos", sa.Column("interconnection", sa.String(20), nullable=True))
    op.add_column("isos", sa.Column("rto_neighbor", sa.String(10), nullable=True))
    op.add_column("isos", sa.Column("rto_neighbor_secondary", sa.String(10), nullable=True))
    op.add_column("isos", sa.Column("interface_points", sa.JSON(), nullable=True))
    op.add_column("isos", sa.Column("latitude", sa.Float(), nullable=True))
    op.add_column("isos", sa.Column("longitude", sa.Float(), nullable=True))
    op.add_column("isos", sa.Column("transfer_limit_mw", sa.Float(), nullable=True))
    op.add_column("isos", sa.Column("transfer_limit_method", sa.String(20), nullable=True))
    op.add_column("isos", sa.Column("ba_extra", sa.JSON(), nullable=True))

    # Mark existing 7 ISOs as RTOs
    op.execute("UPDATE isos SET is_rto = true WHERE ba_code IS NULL")

    # ============================================================
    # Step 2: Create computation_runs table
    # ============================================================
    op.create_table(
        "computation_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("run_type", sa.String(50), nullable=False),
        sa.Column("iso_id", sa.Integer(), sa.ForeignKey("isos.id"), nullable=True),
        sa.Column("period_year", sa.Integer(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(20), server_default="running"),
        sa.Column("parameters_json", sa.JSON(), nullable=True),
        sa.Column("metrics_json", sa.JSON(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
    )

    # ============================================================
    # Step 3: Create constraint_profiles table
    # ============================================================
    op.create_table(
        "constraint_profiles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("location_level", sa.String(20), nullable=False),
        sa.Column("location_id", sa.Integer(), nullable=False),
        sa.Column("constraint_type", sa.String(20), nullable=False),
        sa.Column("source_type", sa.String(50), nullable=False),
        sa.Column("period_year", sa.Integer(), nullable=False),
        sa.Column("profile_12x24", sa.JSON(), nullable=False),
        sa.Column("peak_intensity", sa.Float(), nullable=False),
        sa.Column("peak_month", sa.SmallInteger(), nullable=False),
        sa.Column("peak_hour", sa.SmallInteger(), nullable=False),
        sa.Column("mean_intensity", sa.Float(), nullable=False),
        sa.Column("total_constrained_hours", sa.Integer(), nullable=False),
        sa.Column("constrained_hours_pct", sa.Float(), nullable=False),
        sa.Column("severity_score", sa.Float(), nullable=False),
        sa.Column("severity_tier", sa.String(20), nullable=False),
        sa.Column("avg_marginal_cost", sa.Float(), nullable=True),
        sa.Column("annual_cost", sa.Float(), nullable=True),
        sa.Column("computed_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("computation_run_id", sa.Integer(), sa.ForeignKey("computation_runs.id"), nullable=True),
        sa.UniqueConstraint(
            "location_level", "location_id", "constraint_type",
            "source_type", "period_year",
            name="uq_constraint_profile"),
    )
    op.create_index("ix_cp_location", "constraint_profiles", ["location_level", "location_id"])
    op.create_index("ix_cp_type_year", "constraint_profiles", ["constraint_type", "period_year"])
    op.create_index("ix_cp_severity", "constraint_profiles", ["severity_score"])

    # ============================================================
    # Step 4: Create constraint_annotations table
    # ============================================================
    op.create_table(
        "constraint_annotations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("constraint_profile_id", sa.Integer(), sa.ForeignKey("constraint_profiles.id"), nullable=False),
        sa.Column("annotation_type", sa.String(30), nullable=False),
        sa.Column("utility_id", sa.Integer(), sa.ForeignKey("utilities.id"), nullable=True),
        sa.Column("filing_id", sa.Integer(), sa.ForeignKey("filings.id"), nullable=True),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("planned_solution", sa.Text(), nullable=True),
        sa.Column("deferral_value_estimate", sa.Float(), nullable=True),
        sa.Column("source_url", sa.String(1000), nullable=True),
        sa.Column("source_document", sa.String(500), nullable=True),
        sa.Column("confidence", sa.Float(), server_default="0.5"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_ca_profile", "constraint_annotations", ["constraint_profile_id"])
    op.create_index("ix_ca_type", "constraint_annotations", ["annotation_type"])
    op.create_index("ix_ca_utility", "constraint_annotations", ["utility_id"])

    # ============================================================
    # Step 5: Create der_profiles table
    # ============================================================
    op.create_table(
        "der_profiles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("der_type", sa.String(50), nullable=False),
        sa.Column("eac_category", sa.String(20), nullable=False),
        sa.Column("profile_source", sa.String(50), nullable=False),
        sa.Column("location_id", sa.Integer(), nullable=True),
        sa.Column("profile_12x24", sa.JSON(), nullable=True),
        sa.Column("is_dispatchable", sa.Boolean(), server_default="false"),
        sa.Column("max_dispatch_hours", sa.Float(), nullable=True),
        sa.Column("dispatch_power_mw", sa.Float(), nullable=True),
        sa.Column("ramp_rate_mw_per_min", sa.Float(), nullable=True),
        sa.Column("capacity_factor", sa.Float(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("der_type", "profile_source", "location_id",
                            name="uq_der_profile"),
    )
    op.create_index("ix_dp_type", "der_profiles", ["der_type"])

    # ============================================================
    # Step 6: Create constraint_der_intersections table
    # ============================================================
    op.create_table(
        "constraint_der_intersections",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("constraint_profile_id", sa.Integer(), sa.ForeignKey("constraint_profiles.id"), nullable=False),
        sa.Column("der_profile_id", sa.Integer(), sa.ForeignKey("der_profiles.id"), nullable=False),
        sa.Column("coincidence_factor", sa.Float(), nullable=False),
        sa.Column("overlap_hours", sa.Integer(), nullable=False),
        sa.Column("overlap_12x24", sa.JSON(), nullable=True),
        sa.Column("value_per_kw_year", sa.Float(), nullable=False),
        sa.Column("value_tier", sa.String(20), nullable=False),
        sa.Column("value_breakdown", sa.JSON(), nullable=True),
        sa.Column("computed_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("constraint_profile_id", "der_profile_id", name="uq_cdi"),
    )
    op.create_index("ix_cdi_constraint", "constraint_der_intersections", ["constraint_profile_id"])
    op.create_index("ix_cdi_der", "constraint_der_intersections", ["der_profile_id"])
    op.create_index("ix_cdi_value", "constraint_der_intersections", ["value_per_kw_year"])

    # ============================================================
    # Step 7: Create location_value_stacks table
    # ============================================================
    op.create_table(
        "location_value_stacks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("location_level", sa.String(20), nullable=False),
        sa.Column("location_id", sa.Integer(), nullable=False),
        sa.Column("der_profile_id", sa.Integer(), sa.ForeignKey("der_profiles.id"), nullable=False),
        sa.Column("congestion_value_per_kw_year", sa.Float(), nullable=True, server_default="0.0"),
        sa.Column("loading_value_per_kw_year", sa.Float(), nullable=True, server_default="0.0"),
        sa.Column("capacity_value_per_kw_year", sa.Float(), nullable=True, server_default="0.0"),
        sa.Column("import_stress_value_per_kw_year", sa.Float(), nullable=True, server_default="0.0"),
        sa.Column("total_value_per_kw_year", sa.Float(), nullable=False),
        sa.Column("composite_coincidence_factor", sa.Float(), nullable=False),
        sa.Column("value_tier", sa.String(20), nullable=False),
        sa.Column("constraint_layers", sa.JSON(), nullable=True),
        sa.Column("period_year", sa.Integer(), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("location_level", "location_id", "der_profile_id",
                            "period_year", name="uq_lvs"),
    )
    op.create_index("ix_lvs_location", "location_value_stacks", ["location_level", "location_id"])
    op.create_index("ix_lvs_value", "location_value_stacks", ["total_value_per_kw_year"])
    op.create_index("ix_lvs_tier", "location_value_stacks", ["value_tier"])

    # ============================================================
    # Step 8: Migrate BA data from balancing_authorities into isos
    # ============================================================
    op.execute("""
        INSERT INTO isos (iso_code, iso_name, timezone, has_decomposition, has_node_pricing,
                          ba_code, ba_name, is_rto, region, interconnection,
                          rto_neighbor, rto_neighbor_secondary, interface_points,
                          latitude, longitude, transfer_limit_mw, transfer_limit_method,
                          ba_extra)
        SELECT ba_code, ba_name, 'UTC', false, false,
               ba_code, ba_name, is_rto, region, interconnection,
               rto_neighbor, rto_neighbor_secondary, interface_points,
               latitude, longitude, transfer_limit_mw, transfer_limit_method,
               ba_extra
        FROM balancing_authorities
        ON CONFLICT (iso_code) DO NOTHING
    """)

    # Set parent_iso_id for BAs that have an rto_neighbor matching an RTO iso_code
    op.execute("""
        UPDATE isos child
        SET parent_iso_id = parent.id
        FROM isos parent
        WHERE child.rto_neighbor IS NOT NULL
          AND child.ba_code IS NOT NULL
          AND UPPER(child.rto_neighbor) = UPPER(parent.iso_code)
          AND parent.is_rto = true
    """)

    # ============================================================
    # Step 9: Rewire ba_hourly_data FK from balancing_authorities to isos
    # ============================================================
    # Drop unique index and FK first to avoid collisions during ID remapping
    op.execute("DROP INDEX IF EXISTS ix_ba_hourly_ba_ts")
    op.drop_constraint("ba_hourly_data_ba_id_fkey", "ba_hourly_data", type_="foreignkey")

    # Remap ba_id from old BA IDs to new ISO IDs via a temp mapping column
    op.execute("""
        UPDATE ba_hourly_data bhd
        SET ba_id = i.id
        FROM balancing_authorities ba
        JOIN isos i ON i.ba_code = ba.ba_code
        WHERE bhd.ba_id = ba.id
    """)

    # Recreate unique index and FK pointing to isos
    op.create_index("ix_ba_hourly_ba_ts", "ba_hourly_data", ["ba_id", "timestamp_utc"], unique=True)
    op.create_foreign_key(
        "ba_hourly_data_ba_id_fkey", "ba_hourly_data", "isos",
        ["ba_id"], ["id"])

    # ============================================================
    # Step 10: Rewire congestion_scores FK
    # ============================================================
    # Drop unique index and FK first to avoid collisions during ID remapping
    op.execute("DROP INDEX IF EXISTS ix_congestion_score_ba_period")
    op.drop_constraint("congestion_scores_ba_id_fkey", "congestion_scores", type_="foreignkey")

    op.execute("""
        UPDATE congestion_scores cs
        SET ba_id = i.id
        FROM balancing_authorities ba
        JOIN isos i ON i.ba_code = ba.ba_code
        WHERE cs.ba_id = ba.id
    """)

    # Recreate unique index and FK pointing to isos
    op.create_index("ix_congestion_score_ba_period", "congestion_scores",
                    ["ba_id", "period_start", "period_type"], unique=True)
    op.create_foreign_key(
        "congestion_scores_ba_id_fkey", "congestion_scores", "isos",
        ["ba_id"], ["id"])

    # ============================================================
    # Step 11: Drop balancing_authorities table
    # ============================================================
    op.drop_index("ix_ba_code", table_name="balancing_authorities")
    op.drop_table("balancing_authorities")

    # ============================================================
    # Step 12: Create materialized views (empty, WITH NO DATA)
    # ============================================================
    op.execute("""
        CREATE MATERIALIZED VIEW IF NOT EXISTS mv_zone_constraint_summary AS
        SELECT
            i.iso_code,
            z.zone_code,
            z.zone_name,
            cp.constraint_type AS primary_constraint_type,
            cp.severity_score,
            cp.severity_tier,
            cp.peak_month,
            cp.peak_hour,
            cp.constrained_hours_pct,
            cp.avg_marginal_cost,
            best.der_type AS best_der_type,
            best.value_per_kw_year AS best_der_value
        FROM constraint_profiles cp
        JOIN zones z ON cp.location_id = z.id AND cp.location_level = 'zone'
        JOIN isos i ON z.iso_id = i.id
        LEFT JOIN LATERAL (
            SELECT dp.der_type, cdi.value_per_kw_year
            FROM constraint_der_intersections cdi
            JOIN der_profiles dp ON cdi.der_profile_id = dp.id
            WHERE cdi.constraint_profile_id = cp.id
            ORDER BY cdi.value_per_kw_year DESC
            LIMIT 1
        ) best ON true
        WHERE cp.constraint_type = 'congestion'
        WITH NO DATA
    """)

    op.execute("""
        CREATE MATERIALIZED VIEW IF NOT EXISTS mv_location_rankings AS
        SELECT
            lvs.location_level,
            lvs.location_id,
            dp.der_type,
            lvs.total_value_per_kw_year,
            lvs.value_tier,
            lvs.composite_coincidence_factor,
            lvs.period_year
        FROM location_value_stacks lvs
        JOIN der_profiles dp ON lvs.der_profile_id = dp.id
        WHERE dp.profile_source = 'canonical'
        WITH NO DATA
    """)


def downgrade() -> None:
    # Drop materialized views
    op.execute("DROP MATERIALIZED VIEW IF EXISTS mv_location_rankings")
    op.execute("DROP MATERIALIZED VIEW IF EXISTS mv_zone_constraint_summary")

    # Recreate balancing_authorities table
    op.create_table(
        "balancing_authorities",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ba_code", sa.String(10), unique=True, nullable=False),
        sa.Column("ba_name", sa.String(200)),
        sa.Column("region", sa.String(50)),
        sa.Column("interconnection", sa.String(20)),
        sa.Column("is_rto", sa.Boolean(), server_default="false"),
        sa.Column("rto_neighbor", sa.String(10)),
        sa.Column("rto_neighbor_secondary", sa.String(10)),
        sa.Column("interface_points", sa.JSON()),
        sa.Column("latitude", sa.Float()),
        sa.Column("longitude", sa.Float()),
        sa.Column("transfer_limit_mw", sa.Float()),
        sa.Column("transfer_limit_method", sa.String(20)),
        sa.Column("ba_extra", sa.JSON()),
    )
    op.create_index("ix_ba_code", "balancing_authorities", ["ba_code"], unique=True)

    # Migrate BA data back from isos to balancing_authorities
    op.execute("""
        INSERT INTO balancing_authorities (ba_code, ba_name, region, interconnection,
                                           is_rto, rto_neighbor, rto_neighbor_secondary,
                                           interface_points, latitude, longitude,
                                           transfer_limit_mw, transfer_limit_method, ba_extra)
        SELECT ba_code, ba_name, region, interconnection,
               is_rto, rto_neighbor, rto_neighbor_secondary,
               interface_points, latitude, longitude,
               transfer_limit_mw, transfer_limit_method, ba_extra
        FROM isos
        WHERE ba_code IS NOT NULL
    """)

    # Rewire FKs back
    op.drop_constraint("congestion_scores_ba_id_fkey", "congestion_scores", type_="foreignkey")
    op.execute("""
        UPDATE congestion_scores
        SET ba_id = (
            SELECT ba.id FROM balancing_authorities ba
            WHERE ba.ba_code = (
                SELECT i.ba_code FROM isos i WHERE i.id = congestion_scores.ba_id
            )
        )
    """)
    op.create_foreign_key(
        "congestion_scores_ba_id_fkey", "congestion_scores", "balancing_authorities",
        ["ba_id"], ["id"])

    op.drop_constraint("ba_hourly_data_ba_id_fkey", "ba_hourly_data", type_="foreignkey")
    op.execute("""
        UPDATE ba_hourly_data
        SET ba_id = (
            SELECT ba.id FROM balancing_authorities ba
            WHERE ba.ba_code = (
                SELECT i.ba_code FROM isos i WHERE i.id = ba_hourly_data.ba_id
            )
        )
    """)
    op.create_foreign_key(
        "ba_hourly_data_ba_id_fkey", "ba_hourly_data", "balancing_authorities",
        ["ba_id"], ["id"])

    # Delete BA rows from isos
    op.execute("DELETE FROM isos WHERE ba_code IS NOT NULL")

    # Drop new tables in reverse order
    op.drop_table("location_value_stacks")
    op.drop_table("constraint_der_intersections")
    op.drop_table("der_profiles")
    op.drop_table("constraint_annotations")
    op.drop_table("constraint_profiles")
    op.drop_table("computation_runs")

    # Remove BA columns from isos
    op.drop_column("isos", "ba_extra")
    op.drop_column("isos", "transfer_limit_method")
    op.drop_column("isos", "transfer_limit_mw")
    op.drop_column("isos", "longitude")
    op.drop_column("isos", "latitude")
    op.drop_column("isos", "interface_points")
    op.drop_column("isos", "rto_neighbor_secondary")
    op.drop_column("isos", "rto_neighbor")
    op.drop_column("isos", "interconnection")
    op.drop_column("isos", "region")
    op.drop_column("isos", "parent_iso_id")
    op.drop_column("isos", "is_rto")
    op.drop_column("isos", "ba_name")
    op.drop_column("isos", "ba_code")
