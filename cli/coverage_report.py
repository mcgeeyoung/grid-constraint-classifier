"""Data coverage report CLI.

Queries existing data across all tables to compute coverage metrics
by utility, state, ISO, and data type. Optionally saves coverage
records to the data_coverage table.

Usage:
  python -m cli.coverage_report
  python -m cli.coverage_report --state CA
  python -m cli.coverage_report --by-iso
  python -m cli.coverage_report --by-type
  python -m cli.coverage_report --save
  python -m cli.coverage_report --iso-sources
"""

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import func, distinct

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def cmd_summary(args):
    """Print overall data coverage summary."""
    from app.database import SessionLocal
    from app.models import (
        Utility, HostingCapacityRecord, GridConstraint, LoadForecast,
        ResourceNeed, InterconnectionQueue, Filing, DocketWatch, Regulator,
    )

    session = SessionLocal()
    try:
        # Count records across all tables
        counts = {
            "Utilities": session.query(Utility).count(),
            "  with EIA ID": session.query(Utility).filter(Utility.eia_id.isnot(None)).count(),
            "Regulators": session.query(Regulator).count(),
            "Filings": session.query(Filing).count(),
            "Docket Watches": session.query(DocketWatch).count(),
            "HC Records": session.query(HostingCapacityRecord).count(),
            "Grid Constraints": session.query(GridConstraint).count(),
            "Load Forecasts": session.query(LoadForecast).count(),
            "Resource Needs": session.query(ResourceNeed).count(),
            "Intercon. Queue": session.query(InterconnectionQueue).count(),
        }

        print("\n=== Data Coverage Summary ===\n")
        print(f"{'Table':<25} {'Records':>10}")
        print("-" * 37)
        for name, count in counts.items():
            indent = "  " if name.startswith("  ") else ""
            label = name.strip()
            print(f"{indent}{label:<23} {count:>10,}")

        # State coverage
        states_with_data = (
            session.query(distinct(Utility.state))
            .filter(Utility.state.isnot(None))
            .count()
        )
        print(f"\nStates with utility data: {states_with_data}/51")

        # HC utility coverage
        hc_utilities = (
            session.query(distinct(HostingCapacityRecord.utility_id))
            .count()
        )
        total_utilities = session.query(Utility).count()
        print(f"Utilities with HC data:   {hc_utilities}/{total_utilities}")

        # ISO coverage
        from app.models import ISO
        iso_count = session.query(ISO).count()
        print(f"ISOs registered:          {iso_count}")

        if args.state:
            _print_state_detail(session, args.state)

    finally:
        session.close()


def cmd_by_state(args):
    """Show coverage broken down by state."""
    from app.database import SessionLocal
    from app.models import Utility, HostingCapacityRecord, GridConstraint, LoadForecast

    session = SessionLocal()
    try:
        # Get states with utilities
        states = (
            session.query(
                Utility.state,
                func.count(Utility.id).label("utility_count"),
            )
            .filter(Utility.state.isnot(None))
            .group_by(Utility.state)
            .order_by(Utility.state)
            .all()
        )

        print(f"\n{'State':<7} {'Utilities':>10} {'HC Recs':>10} {'Constraints':>12} {'Forecasts':>10}")
        print("-" * 55)
        for state, util_count in states:
            hc = (
                session.query(func.count(HostingCapacityRecord.id))
                .join(Utility)
                .filter(Utility.state == state)
                .scalar()
            ) or 0
            gc = (
                session.query(func.count(GridConstraint.id))
                .join(Utility)
                .filter(Utility.state == state)
                .scalar()
            ) or 0
            lf = (
                session.query(func.count(LoadForecast.id))
                .join(Utility)
                .filter(Utility.state == state)
                .scalar()
            ) or 0
            print(f"{state:<7} {util_count:>10,} {hc:>10,} {gc:>12,} {lf:>10,}")

    finally:
        session.close()


def cmd_by_iso(args):
    """Show coverage broken down by ISO/RTO."""
    from app.database import SessionLocal
    from app.models import ISO, Zone, Pnode, TransmissionLine, Substation, InterconnectionQueue

    session = SessionLocal()
    try:
        isos = session.query(ISO).order_by(ISO.iso_code).all()

        print(f"\n{'ISO':<10} {'Zones':>7} {'Pnodes':>8} {'TxLines':>8} {'Subs':>6} {'IQ':>6}")
        print("-" * 50)
        for iso in isos:
            zones = session.query(Zone).filter(Zone.iso_id == iso.id).count()
            pnodes = session.query(Pnode).filter(Pnode.iso_id == iso.id).count()
            tx = session.query(TransmissionLine).filter(TransmissionLine.iso_id == iso.id).count()
            subs = session.query(Substation).filter(Substation.iso_id == iso.id).count()
            iq = session.query(InterconnectionQueue).filter(InterconnectionQueue.iso_id == iso.id).count()
            print(f"{iso.iso_code:<10} {zones:>7,} {pnodes:>8,} {tx:>8,} {subs:>6,} {iq:>6,}")

    finally:
        session.close()


def cmd_by_type(args):
    """Show coverage by data type."""
    from app.database import SessionLocal
    from app.models import (
        HostingCapacityRecord, GridConstraint, LoadForecast,
        ResourceNeed, InterconnectionQueue, Filing, FilingDocument,
    )

    session = SessionLocal()
    try:
        types = [
            ("Hosting Capacity", HostingCapacityRecord, None),
            ("Grid Constraints", GridConstraint, None),
            ("Load Forecasts", LoadForecast, None),
            ("Resource Needs", ResourceNeed, None),
            ("Interconnection Queue", InterconnectionQueue, None),
            ("Filings", Filing, None),
            ("Filing Documents", FilingDocument, None),
        ]

        print(f"\n{'Data Type':<25} {'Records':>10} {'Utilities':>10}")
        print("-" * 47)
        for name, model, _ in types:
            count = session.query(model).count()
            # Count distinct utilities if model has utility_id
            if hasattr(model, "utility_id"):
                util_count = (
                    session.query(distinct(model.utility_id))
                    .filter(model.utility_id.isnot(None))
                    .count()
                )
            else:
                util_count = 0
            print(f"{name:<25} {count:>10,} {util_count:>10,}")

    finally:
        session.close()


def cmd_iso_sources(args):
    """Show ISO/RTO planning data source coverage."""
    from adapters.federal_data.iso_planning import summarize_coverage

    coverage = summarize_coverage()

    print("\n=== ISO/RTO Planning Data Source Coverage ===\n")
    print(f"{'ISO':<10} {'Sources':>8} {'Queue':>6} {'Forecast':>9} {'TxPlan':>7} {'Categories'}")
    print("-" * 70)
    for iso_code, info in sorted(coverage.items()):
        queue = "Y" if info["has_queue"] else "-"
        forecast = "Y" if info["has_forecast"] else "-"
        tx = "Y" if info["has_transmission_plan"] else "-"
        cats = ", ".join(info["categories"])
        print(f"{iso_code:<10} {info['source_count']:>8} {queue:>6} {forecast:>9} {tx:>7} {cats}")


def cmd_save(args):
    """Compute and save coverage metrics to data_coverage table."""
    from app.database import SessionLocal
    from app.models import Utility, DataCoverage
    from app.models import (
        HostingCapacityRecord, GridConstraint, LoadForecast,
        ResourceNeed, InterconnectionQueue,
    )
    from datetime import datetime, timezone

    session = SessionLocal()
    now = datetime.now(timezone.utc)

    try:
        # Coverage by utility
        utilities = session.query(Utility).all()
        saved = 0

        data_types = [
            ("hosting_capacity", HostingCapacityRecord),
            ("grid_constraint", GridConstraint),
            ("load_forecast", LoadForecast),
            ("resource_need", ResourceNeed),
            ("interconnection_queue", InterconnectionQueue),
        ]

        for utility in utilities:
            for dtype, model in data_types:
                count = (
                    session.query(model)
                    .filter(model.utility_id == utility.id)
                    .count()
                )

                # Upsert coverage record
                existing = (
                    session.query(DataCoverage)
                    .filter(
                        DataCoverage.entity_type == "utility",
                        DataCoverage.entity_id == utility.id,
                        DataCoverage.data_type == dtype,
                    )
                    .first()
                )

                if existing:
                    existing.record_count = count
                    existing.has_data = count > 0
                    existing.last_checked_at = now
                else:
                    dc = DataCoverage(
                        entity_type="utility",
                        entity_id=utility.id,
                        entity_name=utility.utility_name,
                        state=utility.state,
                        data_type=dtype,
                        has_data=count > 0,
                        record_count=count,
                        last_checked_at=now,
                    )
                    session.add(dc)
                    saved += 1

        session.commit()
        print(f"Saved {saved} new coverage records (updated existing)")

    except Exception as e:
        session.rollback()
        logger.error(f"Save failed: {e}")
    finally:
        session.close()


def _print_state_detail(session, state: str):
    """Print detailed coverage for a specific state."""
    from app.models import Utility, Regulator

    print(f"\n--- {state} Detail ---")

    reg = session.query(Regulator).filter(Regulator.state == state).first()
    if reg:
        print(f"Regulator: {reg.name} ({reg.abbreviation})")
        print(f"  eFiling: {reg.efiling_url or 'N/A'}")

    utilities = (
        session.query(Utility)
        .filter(Utility.state == state)
        .order_by(Utility.utility_name)
        .all()
    )
    print(f"Utilities: {len(utilities)}")
    for u in utilities[:10]:
        eia = f" (EIA: {u.eia_id})" if u.eia_id else ""
        print(f"  {u.utility_name}{eia}")
    if len(utilities) > 10:
        print(f"  ... and {len(utilities) - 10} more")


def main():
    parser = argparse.ArgumentParser(description="Data coverage report")
    parser.add_argument("--state", help="Show detail for specific state")

    sub = parser.add_subparsers(dest="command")

    sub.add_parser("by-state", help="Coverage by state")
    sub.add_parser("by-iso", help="Coverage by ISO/RTO")
    sub.add_parser("by-type", help="Coverage by data type")
    sub.add_parser("iso-sources", help="ISO/RTO planning data sources")
    sub.add_parser("save", help="Compute and save coverage metrics to DB")

    args = parser.parse_args()

    if args.command == "by-state":
        cmd_by_state(args)
    elif args.command == "by-iso":
        cmd_by_iso(args)
    elif args.command == "by-type":
        cmd_by_type(args)
    elif args.command == "iso-sources":
        cmd_iso_sources(args)
    elif args.command == "save":
        cmd_save(args)
    else:
        cmd_summary(args)


if __name__ == "__main__":
    main()
