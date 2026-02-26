"""Add grid intelligence tables (feeders, circuits, der_locations, der_valuations, hierarchy_scores)

Revision ID: d6f0a4b58c7e
Revises: c5e9f3a47b6d
Create Date: 2026-02-26
"""
from alembic import op
import sqlalchemy as sa

revision = "d6f0a4b58c7e"
down_revision = "c5e9f3a47b6d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Feeders
    op.create_table(
        "feeders",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("substation_id", sa.Integer(), sa.ForeignKey("substations.id"), nullable=False),
        sa.Column("feeder_id_external", sa.String(100), nullable=True),
        sa.Column("capacity_mw", sa.Float(), nullable=True),
        sa.Column("peak_loading_mw", sa.Float(), nullable=True),
        sa.Column("peak_loading_pct", sa.Float(), nullable=True),
        sa.Column("voltage_kv", sa.Float(), nullable=True),
        sa.Column("geometry_json", sa.JSON(), nullable=True),
    )
    op.create_index("ix_feeders_substation_id", "feeders", ["substation_id"])

    # Circuits
    op.create_table(
        "circuits",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("feeder_id", sa.Integer(), sa.ForeignKey("feeders.id"), nullable=False),
        sa.Column("circuit_id_external", sa.String(100), nullable=True),
        sa.Column("capacity_mw", sa.Float(), nullable=True),
        sa.Column("peak_loading_mw", sa.Float(), nullable=True),
        sa.Column("lat", sa.Float(), nullable=True),
        sa.Column("lon", sa.Float(), nullable=True),
    )
    op.create_index("ix_circuits_feeder_id", "circuits", ["feeder_id"])

    # DER Locations
    op.create_table(
        "der_locations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("iso_id", sa.Integer(), sa.ForeignKey("isos.id"), nullable=False),
        sa.Column("zone_id", sa.Integer(), sa.ForeignKey("zones.id"), nullable=True),
        sa.Column("substation_id", sa.Integer(), sa.ForeignKey("substations.id"), nullable=True),
        sa.Column("feeder_id", sa.Integer(), sa.ForeignKey("feeders.id"), nullable=True),
        sa.Column("circuit_id", sa.Integer(), sa.ForeignKey("circuits.id"), nullable=True),
        sa.Column("nearest_pnode_id", sa.Integer(), sa.ForeignKey("pnodes.id"), nullable=True),
        sa.Column("der_type", sa.String(50), nullable=False),
        sa.Column("eac_category", sa.String(30), nullable=True),
        sa.Column("capacity_mw", sa.Float(), nullable=False),
        sa.Column("lat", sa.Float(), nullable=True),
        sa.Column("lon", sa.Float(), nullable=True),
        sa.Column("wattcarbon_asset_id", sa.String(100), nullable=True),
        sa.Column("source", sa.String(30), nullable=False, server_default="hypothetical"),
    )
    op.create_index("ix_der_locations_iso_id", "der_locations", ["iso_id"])
    op.create_index("ix_der_locations_zone_id", "der_locations", ["zone_id"])

    # DER Valuations
    op.create_table(
        "der_valuations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("pipeline_run_id", sa.Integer(), sa.ForeignKey("pipeline_runs.id"), nullable=False),
        sa.Column("der_location_id", sa.Integer(), sa.ForeignKey("der_locations.id"), nullable=False),
        sa.Column("zone_congestion_value", sa.Float(), nullable=True),
        sa.Column("pnode_multiplier", sa.Float(), nullable=True),
        sa.Column("substation_loading_value", sa.Float(), nullable=True),
        sa.Column("feeder_capacity_value", sa.Float(), nullable=True),
        sa.Column("total_constraint_relief_value", sa.Float(), nullable=True),
        sa.Column("coincidence_factor", sa.Float(), nullable=True),
        sa.Column("effective_capacity_mw", sa.Float(), nullable=True),
        sa.Column("value_tier", sa.String(20), nullable=True),
        sa.Column("value_breakdown", sa.JSON(), nullable=True),
        sa.UniqueConstraint("pipeline_run_id", "der_location_id", name="uq_der_valuations"),
    )
    op.create_index("ix_der_valuations_pipeline_run_id", "der_valuations", ["pipeline_run_id"])

    # Hierarchy Scores
    op.create_table(
        "hierarchy_scores",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("pipeline_run_id", sa.Integer(), sa.ForeignKey("pipeline_runs.id"), nullable=False),
        sa.Column("level", sa.String(20), nullable=False),
        sa.Column("entity_id", sa.Integer(), nullable=False),
        sa.Column("congestion_score", sa.Float(), nullable=True),
        sa.Column("loading_score", sa.Float(), nullable=True),
        sa.Column("combined_score", sa.Float(), nullable=True),
        sa.Column("constraint_tier", sa.String(20), nullable=True),
        sa.Column("constraint_loadshape", sa.JSON(), nullable=True),
        sa.UniqueConstraint("pipeline_run_id", "level", "entity_id", name="uq_hierarchy_scores"),
    )
    op.create_index("ix_hierarchy_scores_pipeline_run_id", "hierarchy_scores", ["pipeline_run_id"])
    op.create_index("ix_hierarchy_scores_level", "hierarchy_scores", ["level", "entity_id"])


def downgrade() -> None:
    op.drop_table("hierarchy_scores")
    op.drop_table("der_valuations")
    op.drop_table("der_locations")
    op.drop_table("circuits")
    op.drop_table("feeders")
