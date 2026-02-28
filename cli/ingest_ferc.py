"""FERC data ingestion CLI.

Operations:
  - Search FERC eLibrary for filings
  - Download Form 714 bulk data
  - Parse Form 714 respondents and planning areas
  - Import Form 714 planning area data into load_forecasts table

Usage:
  python -m cli.ingest_ferc search --keyword "transmission plan" --max 20
  python -m cli.ingest_ferc search --docket ER24-1234
  python -m cli.ingest_ferc download-714 --dest data/ferc714
  python -m cli.ingest_ferc parse-714 --file data/ferc714/ferc714_bulk.zip --respondents
  python -m cli.ingest_ferc parse-714 --file data/ferc714/ferc714_bulk.zip --planning-areas --year 2023
  python -m cli.ingest_ferc import-714 --file data/ferc714/ferc714_bulk.zip --year 2023
"""

import argparse
import json
import logging
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def cmd_search(args):
    """Search FERC eLibrary."""
    from adapters.federal_data.ferc_elibrary import FERCeLibraryScraper

    scraper = FERCeLibraryScraper()

    date_from = None
    date_to = None
    if args.date_from:
        date_from = date.fromisoformat(args.date_from)
    if args.date_to:
        date_to = date.fromisoformat(args.date_to)

    results = scraper.search(
        keyword=args.keyword,
        docket_number=args.docket,
        date_from=date_from,
        date_to=date_to,
        category=args.category,
        max_results=args.max,
    )

    if not results:
        print("No results found.")
        return

    print(f"\nFound {len(results)} filings:\n")
    print(f"{'Accession':<20} {'Docket':<15} {'Date':<12} {'Description'}")
    print("-" * 80)
    for f in results:
        desc = (f.description or "")[:40]
        dt = f.filing_date.isoformat() if f.filing_date else ""
        print(f"{f.accession_number:<20} {(f.docket_number or ''):<15} {dt:<12} {desc}")

    if args.output_json:
        output = [
            {
                "accession_number": f.accession_number,
                "docket_number": f.docket_number,
                "description": f.description,
                "filing_date": f.filing_date.isoformat() if f.filing_date else None,
                "category": f.category,
                "filer": f.filer,
            }
            for f in results
        ]
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        with open(args.output_json, "w") as fp:
            json.dump(output, fp, indent=2)
        print(f"\nSaved to {args.output_json}")


def cmd_download_714(args):
    """Download FERC Form 714 bulk data."""
    from adapters.federal_data.ferc714 import FERC714Parser

    parser = FERC714Parser(data_dir=args.dest)
    path = parser.download_bulk_data(dest_dir=args.dest)
    if path:
        print(f"\nDownloaded: {path} ({path.stat().st_size:,} bytes)")
    else:
        print("Download failed. Check logs.")


def cmd_parse_714(args):
    """Parse FERC Form 714 data."""
    from adapters.federal_data.ferc714 import FERC714Parser

    parser = FERC714Parser()

    if not args.file.exists():
        print(f"File not found: {args.file}")
        return

    if args.respondents:
        respondents = parser.parse_respondents(args.file)
        print(f"\n{len(respondents)} respondents:\n")
        print(f"{'ID':<8} {'Name':<50} {'EIA Code':<10} {'State'}")
        print("-" * 80)
        for r in respondents[:50]:
            print(f"{r.respondent_id:<8} {r.respondent_name[:48]:<50} "
                  f"{(str(r.eia_code) if r.eia_code else ''):<10} {r.state or ''}")
        if len(respondents) > 50:
            print(f"  ... and {len(respondents) - 50} more")

    if args.planning_areas:
        areas = parser.parse_planning_areas(args.file, year=args.year)
        print(f"\n{len(areas)} planning area records:\n")
        print(f"{'ID':<8} {'Name':<40} {'Year':<6} {'Peak MW':<12} {'Energy GWh'}")
        print("-" * 80)
        for a in areas[:50]:
            peak = f"{a.peak_demand_mw:,.0f}" if a.peak_demand_mw else ""
            energy = f"{a.annual_energy_gwh:,.0f}" if a.annual_energy_gwh else ""
            print(f"{a.respondent_id:<8} {a.respondent_name[:38]:<40} "
                  f"{a.report_year:<6} {peak:<12} {energy}")
        if len(areas) > 50:
            print(f"  ... and {len(areas) - 50} more")


def cmd_import_714(args):
    """Import Form 714 planning area data into load_forecasts table."""
    from adapters.federal_data.ferc714 import FERC714Parser
    from app.database import SessionLocal
    from app.models import LoadForecast, Utility

    parser = FERC714Parser()

    if not args.file.exists():
        print(f"File not found: {args.file}")
        return

    # Parse planning areas
    areas = parser.parse_planning_areas(args.file, year=args.year)
    if not areas:
        print("No planning area data found.")
        return

    print(f"Found {len(areas)} planning area records")

    if args.dry_run:
        print("DRY RUN: would import these as load forecasts")
        for a in areas[:10]:
            print(f"  {a.respondent_name}: peak={a.peak_demand_mw} MW, "
                  f"energy={a.annual_energy_gwh} GWh ({a.report_year})")
        return

    # Import to DB
    session = SessionLocal()
    try:
        # Build EIA code to utility_id mapping
        utilities = session.query(Utility).filter(Utility.eia_id.isnot(None)).all()
        eia_to_utility = {u.eia_id: u.id for u in utilities}

        saved = 0
        skipped = 0
        for area in areas:
            utility_id = eia_to_utility.get(area.respondent_id)
            if not utility_id:
                skipped += 1
                continue

            lf = LoadForecast(
                utility_id=utility_id,
                forecast_year=area.report_year,
                area_name=area.respondent_name,
                area_type="planning_area",
                peak_demand_mw=area.peak_demand_mw,
                energy_gwh=area.annual_energy_gwh,
                scenario="FERC 714 reported",
            )
            session.add(lf)
            saved += 1

        session.commit()
        print(f"\nImported {saved} load forecast records ({skipped} skipped, no matching utility)")

    except Exception as e:
        session.rollback()
        logger.error(f"Import failed: {e}")
    finally:
        session.close()


def main():
    parser = argparse.ArgumentParser(description="FERC data ingestion")
    sub = parser.add_subparsers(dest="command", required=True)

    # search
    sp = sub.add_parser("search", help="Search FERC eLibrary")
    sp.add_argument("--keyword", help="Search keyword")
    sp.add_argument("--docket", help="Docket number (e.g., ER24-1234)")
    sp.add_argument("--date-from", help="Start date (YYYY-MM-DD)")
    sp.add_argument("--date-to", help="End date (YYYY-MM-DD)")
    sp.add_argument("--category", help="Filing category")
    sp.add_argument("--max", type=int, default=25, help="Max results")
    sp.add_argument("--output-json", type=Path, help="Save results to JSON")
    sp.set_defaults(func=cmd_search)

    # download-714
    sp = sub.add_parser("download-714", help="Download FERC Form 714 bulk data")
    sp.add_argument("--dest", type=Path, default=Path("data/ferc714"), help="Destination directory")
    sp.set_defaults(func=cmd_download_714)

    # parse-714
    sp = sub.add_parser("parse-714", help="Parse FERC Form 714 data")
    sp.add_argument("--file", type=Path, required=True, help="Path to Form 714 ZIP file")
    sp.add_argument("--respondents", action="store_true", help="List respondents")
    sp.add_argument("--planning-areas", action="store_true", help="Show planning area data")
    sp.add_argument("--year", type=int, help="Filter by year")
    sp.set_defaults(func=cmd_parse_714)

    # import-714
    sp = sub.add_parser("import-714", help="Import Form 714 into load_forecasts")
    sp.add_argument("--file", type=Path, required=True, help="Path to Form 714 ZIP file")
    sp.add_argument("--year", type=int, help="Year to import")
    sp.add_argument("--dry-run", action="store_true", help="Preview without saving")
    sp.set_defaults(func=cmd_import_714)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
