"""Add data pipeline tables: regulators, filings, filing_documents,
grid_constraints, load_forecasts, resource_needs. Extend utilities with
EIA-861 fields (eia_id, utility_type, state, regulator_id, customers, sales).

Revision ID: j2e5f9a03b1c
Revises: i1d4e8f92a0b
Create Date: 2026-02-28
"""

from alembic import op
import sqlalchemy as sa
from geoalchemy2 import Geometry

# revision identifiers, used by Alembic
revision = "j2e5f9a03b1c"
down_revision = "i1d4e8f92a0b"
branch_labels = None
depends_on = None


def upgrade():
    # --- regulators ---
    op.create_table(
        "regulators",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("state", sa.String(2), unique=True, nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("abbreviation", sa.String(20)),
        sa.Column("website", sa.String(500)),
        sa.Column("efiling_url", sa.String(500)),
        sa.Column("efiling_type", sa.String(50)),
        sa.Column("api_available", sa.Boolean, server_default="false"),
        sa.Column("notes", sa.String(1000)),
    )

    # --- extend utilities with EIA-861 fields ---
    op.add_column("utilities", sa.Column("eia_id", sa.Integer, unique=True))
    op.add_column("utilities", sa.Column("utility_type", sa.String(30)))
    op.add_column("utilities", sa.Column("state", sa.String(2)))
    op.add_column(
        "utilities",
        sa.Column("regulator_id", sa.Integer, sa.ForeignKey("regulators.id")),
    )
    op.add_column("utilities", sa.Column("customers_total", sa.Integer))
    op.add_column("utilities", sa.Column("sales_mwh", sa.Float))
    op.add_column("utilities", sa.Column("service_territory_counties", sa.JSON))

    op.create_index("ix_utilities_eia_id", "utilities", ["eia_id"])
    op.create_index("ix_utilities_regulator_id", "utilities", ["regulator_id"])
    op.create_index("ix_utilities_state", "utilities", ["state"])

    # --- filings ---
    op.create_table(
        "filings",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("utility_id", sa.Integer, sa.ForeignKey("utilities.id"), nullable=False),
        sa.Column("regulator_id", sa.Integer, sa.ForeignKey("regulators.id")),
        sa.Column("docket_number", sa.String(100)),
        sa.Column("filing_type", sa.String(50), nullable=False),
        sa.Column("title", sa.String(500)),
        sa.Column("filed_date", sa.Date),
        sa.Column("source_url", sa.String(1000)),
        sa.Column("raw_document_path", sa.String(500)),
        sa.Column("status", sa.String(30), server_default="discovered"),
        sa.Column("metadata_json", sa.JSON),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_filings_utility", "filings", ["utility_id"])
    op.create_index("ix_filings_regulator", "filings", ["regulator_id"])
    op.create_index("ix_filings_docket", "filings", ["docket_number"])
    op.create_index("ix_filings_type", "filings", ["filing_type"])

    # --- filing_documents ---
    op.create_table(
        "filing_documents",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("filing_id", sa.Integer, sa.ForeignKey("filings.id"), nullable=False),
        sa.Column("document_type", sa.String(50)),
        sa.Column("filename", sa.String(300)),
        sa.Column("mime_type", sa.String(100)),
        sa.Column("raw_path", sa.String(500)),
        sa.Column("extracted_text", sa.Text),
        sa.Column("parsed_data", sa.JSON),
        sa.Column("status", sa.String(30), server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_filing_docs_filing", "filing_documents", ["filing_id"])

    # --- grid_constraints ---
    op.create_table(
        "grid_constraints",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("utility_id", sa.Integer, sa.ForeignKey("utilities.id"), nullable=False),
        sa.Column("filing_id", sa.Integer, sa.ForeignKey("filings.id")),
        sa.Column("constraint_type", sa.String(50), nullable=False),
        sa.Column("location_type", sa.String(50)),
        sa.Column("location_name", sa.String(300)),
        sa.Column("location_geom", Geometry("POINT", srid=4326)),
        sa.Column("current_capacity_mw", sa.Float),
        sa.Column("forecasted_load_mw", sa.Float),
        sa.Column("constraint_year", sa.Integer),
        sa.Column("headroom_mw", sa.Float),
        sa.Column("notes", sa.String(1000)),
        sa.Column("raw_source_reference", sa.String(300)),
        sa.Column("confidence", sa.String(20)),
    )
    op.create_index("ix_gc_utility", "grid_constraints", ["utility_id"])
    op.create_index("ix_gc_filing", "grid_constraints", ["filing_id"])
    op.create_index("ix_gc_type", "grid_constraints", ["constraint_type"])
    op.create_index(
        "ix_gc_geom", "grid_constraints", ["location_geom"],
        postgresql_using="gist",
    )

    # --- load_forecasts ---
    op.create_table(
        "load_forecasts",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("utility_id", sa.Integer, sa.ForeignKey("utilities.id"), nullable=False),
        sa.Column("filing_id", sa.Integer, sa.ForeignKey("filings.id")),
        sa.Column("forecast_year", sa.Integer, nullable=False),
        sa.Column("area_name", sa.String(200)),
        sa.Column("area_type", sa.String(50)),
        sa.Column("peak_demand_mw", sa.Float),
        sa.Column("energy_gwh", sa.Float),
        sa.Column("growth_rate_pct", sa.Float),
        sa.Column("scenario", sa.String(30)),
    )
    op.create_index("ix_lf_utility", "load_forecasts", ["utility_id"])
    op.create_index("ix_lf_filing", "load_forecasts", ["filing_id"])
    op.create_index("ix_lf_year", "load_forecasts", ["forecast_year"])

    # --- resource_needs ---
    op.create_table(
        "resource_needs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("utility_id", sa.Integer, sa.ForeignKey("utilities.id"), nullable=False),
        sa.Column("filing_id", sa.Integer, sa.ForeignKey("filings.id")),
        sa.Column("need_type", sa.String(50), nullable=False),
        sa.Column("need_mw", sa.Float),
        sa.Column("need_year", sa.Integer),
        sa.Column("location_type", sa.String(50)),
        sa.Column("location_name", sa.String(200)),
        sa.Column("eligible_resource_types", sa.JSON),
        sa.Column("notes", sa.String(1000)),
    )
    op.create_index("ix_rn_utility", "resource_needs", ["utility_id"])
    op.create_index("ix_rn_filing", "resource_needs", ["filing_id"])
    op.create_index("ix_rn_year", "resource_needs", ["need_year"])


def downgrade():
    op.drop_table("resource_needs")
    op.drop_table("load_forecasts")
    op.drop_table("grid_constraints")
    op.drop_table("filing_documents")
    op.drop_table("filings")

    op.drop_index("ix_utilities_state", table_name="utilities")
    op.drop_index("ix_utilities_regulator_id", table_name="utilities")
    op.drop_index("ix_utilities_eia_id", table_name="utilities")
    op.drop_column("utilities", "service_territory_counties")
    op.drop_column("utilities", "sales_mwh")
    op.drop_column("utilities", "customers_total")
    op.drop_column("utilities", "regulator_id")
    op.drop_column("utilities", "state")
    op.drop_column("utilities", "utility_type")
    op.drop_column("utilities", "eia_id")

    op.drop_table("regulators")
