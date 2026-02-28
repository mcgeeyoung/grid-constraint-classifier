"""Add performance indexes to all FK columns and frequently queried fields.

Revision ID: f8a2b3c4d5e6
Revises: 00810fa89676
Create Date: 2026-02-27

Phase I-0.2: Quick wins - add missing database indexes.
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f8a2b3c4d5e6"
down_revision: str = "00810fa89676"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # data_centers
    op.create_index("ix_data_centers_iso_id", "data_centers", ["iso_id"])
    op.create_index("ix_data_centers_zone_id", "data_centers", ["zone_id"])
    op.create_index("ix_data_centers_status", "data_centers", ["status"])

    # pnodes
    op.create_index("ix_pnodes_iso_id", "pnodes", ["iso_id"])
    op.create_index("ix_pnodes_zone_id", "pnodes", ["zone_id"])

    # zone_lmps (the big table - most critical indexes)
    op.create_index("ix_zone_lmps_iso_id", "zone_lmps", ["iso_id"])
    op.create_index("ix_zone_lmps_zone_id", "zone_lmps", ["zone_id"])
    op.create_index("ix_zone_lmps_timestamp_utc", "zone_lmps", ["timestamp_utc"])
    op.create_index("ix_zone_lmps_iso_zone_ts", "zone_lmps", ["iso_id", "zone_id", "timestamp_utc"])
    op.create_index("ix_zone_lmps_hour_local", "zone_lmps", ["hour_local"])
    op.create_index("ix_zone_lmps_month", "zone_lmps", ["month"])

    # substations
    op.create_index("ix_substations_iso_id", "substations", ["iso_id"])
    op.create_index("ix_substations_zone_id", "substations", ["zone_id"])
    op.create_index("ix_substations_peak_loading_pct", "substations", ["peak_loading_pct"])

    # der_locations
    op.create_index("ix_der_locations_iso_id", "der_locations", ["iso_id"])
    op.create_index("ix_der_locations_zone_id", "der_locations", ["zone_id"])
    op.create_index("ix_der_locations_source", "der_locations", ["source"])
    op.create_index("ix_der_locations_wattcarbon_asset_id", "der_locations", ["wattcarbon_asset_id"])

    # der_valuations
    op.create_index("ix_der_valuations_der_location_id", "der_valuations", ["der_location_id"])
    op.create_index("ix_der_valuations_pipeline_run_id", "der_valuations", ["pipeline_run_id"])
    op.create_index("ix_der_valuations_value_tier", "der_valuations", ["value_tier"])

    # pnode_scores
    op.create_index("ix_pnode_scores_pipeline_run_id", "pnode_scores", ["pipeline_run_id"])
    op.create_index("ix_pnode_scores_pnode_id", "pnode_scores", ["pnode_id"])

    # hierarchy_scores
    op.create_index("ix_hierarchy_scores_pipeline_run_id", "hierarchy_scores", ["pipeline_run_id"])
    op.create_index("ix_hierarchy_scores_level", "hierarchy_scores", ["level"])
    op.create_index("ix_hierarchy_scores_combined_score", "hierarchy_scores", ["combined_score"])

    # zone_classifications
    op.create_index("ix_zone_classifications_pipeline_run_id", "zone_classifications", ["pipeline_run_id"])
    op.create_index("ix_zone_classifications_zone_id", "zone_classifications", ["zone_id"])

    # transmission_lines
    op.create_index("ix_transmission_lines_iso_id", "transmission_lines", ["iso_id"])
    op.create_index("ix_transmission_lines_voltage_kv", "transmission_lines", ["voltage_kv"])


def downgrade() -> None:
    op.drop_index("ix_transmission_lines_voltage_kv", "transmission_lines")
    op.drop_index("ix_transmission_lines_iso_id", "transmission_lines")
    op.drop_index("ix_zone_classifications_zone_id", "zone_classifications")
    op.drop_index("ix_zone_classifications_pipeline_run_id", "zone_classifications")
    op.drop_index("ix_hierarchy_scores_combined_score", "hierarchy_scores")
    op.drop_index("ix_hierarchy_scores_level", "hierarchy_scores")
    op.drop_index("ix_hierarchy_scores_pipeline_run_id", "hierarchy_scores")
    op.drop_index("ix_pnode_scores_pnode_id", "pnode_scores")
    op.drop_index("ix_pnode_scores_pipeline_run_id", "pnode_scores")
    op.drop_index("ix_der_valuations_value_tier", "der_valuations")
    op.drop_index("ix_der_valuations_pipeline_run_id", "der_valuations")
    op.drop_index("ix_der_valuations_der_location_id", "der_valuations")
    op.drop_index("ix_der_locations_wattcarbon_asset_id", "der_locations")
    op.drop_index("ix_der_locations_source", "der_locations")
    op.drop_index("ix_der_locations_zone_id", "der_locations")
    op.drop_index("ix_der_locations_iso_id", "der_locations")
    op.drop_index("ix_substations_peak_loading_pct", "substations")
    op.drop_index("ix_substations_zone_id", "substations")
    op.drop_index("ix_substations_iso_id", "substations")
    op.drop_index("ix_zone_lmps_month", "zone_lmps")
    op.drop_index("ix_zone_lmps_hour_local", "zone_lmps")
    op.drop_index("ix_zone_lmps_iso_zone_ts", "zone_lmps")
    op.drop_index("ix_zone_lmps_timestamp_utc", "zone_lmps")
    op.drop_index("ix_zone_lmps_zone_id", "zone_lmps")
    op.drop_index("ix_zone_lmps_iso_id", "zone_lmps")
    op.drop_index("ix_pnodes_zone_id", "pnodes")
    op.drop_index("ix_pnodes_iso_id", "pnodes")
    op.drop_index("ix_data_centers_status", "data_centers")
    op.drop_index("ix_data_centers_zone_id", "data_centers")
    op.drop_index("ix_data_centers_iso_id", "data_centers")
