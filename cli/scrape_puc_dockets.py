"""PUC Docket Scraper CLI.

Searches state PUC eFiling systems for regulatory proceedings,
lists filings within dockets, and optionally downloads documents.

Usage:
  python -m cli.scrape_puc_dockets --discover                    # discover active dockets for all states
  python -m cli.scrape_puc_dockets --discover --state CA         # discover for California only
  python -m cli.scrape_puc_dockets --search --state CA --keyword "hosting capacity"
  python -m cli.scrape_puc_dockets --list-filings --state CA --docket R.21-06-017
  python -m cli.scrape_puc_dockets --seed-watchlist              # seed docket_watches from JSON
  python -m cli.scrape_puc_dockets --check-watchlist             # check all watched dockets for new filings
  python -m cli.scrape_puc_dockets --list-scrapers               # show available state scrapers
"""

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from adapters.puc_scrapers.registry import get_scraper, list_scrapers, get_all_scrapers

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

WATCHLIST_SEED = Path(__file__).resolve().parent.parent / "data" / "seed" / "docket_watchlist.json"
DOCS_DIR = Path(__file__).resolve().parent.parent / "data" / "puc_documents"


def main():
    parser = argparse.ArgumentParser(description="PUC docket scraper")
    parser.add_argument("--state", help="State code (e.g. CA, VA, NC, NY)")

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--discover", action="store_true", help="Discover active dockets")
    group.add_argument("--search", action="store_true", help="Search dockets by keyword")
    group.add_argument("--list-filings", action="store_true", help="List filings in a docket")
    group.add_argument("--seed-watchlist", action="store_true", help="Seed docket watchlist from JSON")
    group.add_argument("--check-watchlist", action="store_true", help="Check watched dockets for updates")
    group.add_argument("--list-scrapers", action="store_true", help="List available scrapers")

    parser.add_argument("--keyword", help="Search keyword")
    parser.add_argument("--docket", help="Docket number for --list-filings")
    parser.add_argument("--filing-type", help="Filing type filter (IRP, DRP, rate_case, etc.)")
    parser.add_argument("--utility", help="Utility name filter")
    parser.add_argument("--dry-run", action="store_true", help="Print without DB writes")

    args = parser.parse_args()

    if args.list_scrapers:
        _list_scrapers()
        return

    if args.seed_watchlist:
        _seed_watchlist(args.dry_run)
        return

    if args.check_watchlist:
        _check_watchlist(args.state, args.dry_run)
        return

    if args.discover:
        _discover(args.state, args.dry_run)
        return

    if args.search:
        if not args.state:
            parser.error("--search requires --state")
        _search(args.state, args.keyword, args.filing_type, args.utility)
        return

    if args.list_filings:
        if not args.state or not args.docket:
            parser.error("--list-filings requires --state and --docket")
        _list_filings(args.state, args.docket)
        return


def _list_scrapers():
    """Print available scrapers."""
    scrapers = get_all_scrapers()
    print(f"\n{'State':<6} {'PUC Name':<50} {'Base URL'}")
    print("-" * 90)
    for state, scraper in sorted(scrapers.items()):
        print(f"{state:<6} {scraper.puc_name:<50} {scraper.base_url}")
    print(f"\nTotal: {len(scrapers)} scrapers available\n")


def _discover(state: Optional[str], dry_run: bool):
    """Discover active dockets."""
    if state:
        states = [state.upper()]
    else:
        states = list_scrapers()

    all_dockets = []

    for st in states:
        try:
            scraper = get_scraper(st)
            print(f"\n=== {scraper.puc_name} ({st}) ===")
            dockets = scraper.discover_active_dockets()
            all_dockets.extend(dockets)

            for d in dockets:
                status = d.status or "?"
                ftype = d.filing_type or "?"
                title = (d.title or "")[:60]
                print(f"  [{status}] {d.docket_number:<20} {ftype:<15} {title}")

        except Exception as e:
            logger.error(f"Discovery failed for {st}: {e}")

    print(f"\nTotal: {len(all_dockets)} active dockets discovered\n")

    if not dry_run and all_dockets:
        _save_dockets_to_db(all_dockets)


def _search(state: str, keyword: Optional[str], filing_type: Optional[str], utility: Optional[str]):
    """Search dockets by criteria."""
    scraper = get_scraper(state)
    print(f"\n=== Searching {scraper.puc_name} ===")

    dockets = scraper.search_dockets(
        keyword=keyword,
        filing_type=filing_type,
        utility_name=utility,
    )

    if not dockets:
        print("  No results found")
        return

    print(f"\n{'Docket':<25} {'Type':<15} {'Title'}")
    print("-" * 80)
    for d in dockets:
        ftype = d.filing_type or "?"
        title = (d.title or "")[:50]
        print(f"{d.docket_number:<25} {ftype:<15} {title}")

    print(f"\nTotal: {len(dockets)} dockets found\n")


def _list_filings(state: str, docket: str):
    """List filings in a specific docket."""
    scraper = get_scraper(state)
    print(f"\n=== Filings for {docket} ({scraper.puc_name}) ===")

    filings = scraper.list_filings(docket)

    if not filings:
        print("  No filings found (the scraper may need to be adapted for this PUC's HTML structure)")
        return

    print(f"\n{'Date':<12} {'Filed By':<25} {'Docs':>4}  {'Title'}")
    print("-" * 90)
    for f in filings[:50]:  # Limit display
        fdate = str(f.filed_date) if f.filed_date else "?"
        fby = (f.filed_by or "?")[:24]
        docs = len(f.documents)
        title = (f.title or "")[:45]
        print(f"{fdate:<12} {fby:<25} {docs:>4}  {title}")

    if len(filings) > 50:
        print(f"  ... and {len(filings) - 50} more")

    print(f"\nTotal: {len(filings)} filings\n")


def _seed_watchlist(dry_run: bool):
    """Seed docket watchlist from JSON file."""
    with open(WATCHLIST_SEED) as f:
        watches = json.load(f)

    logger.info(f"Loaded {len(watches)} watches from {WATCHLIST_SEED.name}")

    if dry_run:
        print(f"\n{'State':<6} {'Pri':>3} {'Docket':<25} {'Type':<15} {'Title'}")
        print("-" * 90)
        for w in watches:
            title = (w.get("title") or "")[:40]
            print(f"{w['state']:<6} {w.get('priority', 2):>3} {w['docket_number']:<25} {w.get('filing_type', '?'):<15} {title}")
        print(f"\nTotal: {len(watches)} watches (dry run)\n")
        return

    from app.database import SessionLocal
    from app.models import Regulator
    from app.models.docket_watchlist import DocketWatch

    session = SessionLocal()
    try:
        regulators = {r.state: r.id for r in session.query(Regulator).all()}

        created = 0
        updated = 0
        for w in watches:
            existing = (
                session.query(DocketWatch)
                .filter_by(state=w["state"], docket_number=w["docket_number"])
                .first()
            )
            if existing:
                existing.title = w.get("title")
                existing.filing_type = w.get("filing_type")
                existing.priority = w.get("priority", 2)
                existing.notes = w.get("notes")
                updated += 1
            else:
                dw = DocketWatch(
                    state=w["state"],
                    docket_number=w["docket_number"],
                    title=w.get("title"),
                    utility_name=w.get("utility_name"),
                    filing_type=w.get("filing_type"),
                    priority=w.get("priority", 2),
                    notes=w.get("notes"),
                    regulator_id=regulators.get(w["state"]),
                )
                session.add(dw)
                created += 1

        session.commit()
        logger.info(f"Watchlist seeded: {created} created, {updated} updated")
    except Exception as e:
        session.rollback()
        logger.error(f"Failed: {e}")
        raise
    finally:
        session.close()


def _check_watchlist(state: Optional[str], dry_run: bool):
    """Check all watched dockets for new filings."""
    from app.database import SessionLocal
    from app.models.docket_watchlist import DocketWatch

    session = SessionLocal()
    try:
        query = session.query(DocketWatch).filter(DocketWatch.is_active == True)
        if state:
            query = query.filter(DocketWatch.state == state.upper())

        watches = query.order_by(DocketWatch.priority, DocketWatch.state).all()
        logger.info(f"Checking {len(watches)} watched dockets...")

        for watch in watches:
            try:
                scraper = get_scraper(watch.state)
                filings = scraper.list_filings(watch.docket_number)

                new_count = 0
                if watch.last_filing_date:
                    new_filings = [
                        f for f in filings
                        if f.filed_date and datetime.combine(f.filed_date, datetime.min.time()).replace(tzinfo=timezone.utc) > watch.last_filing_date
                    ]
                    new_count = len(new_filings)
                else:
                    new_count = len(filings)

                status = f"{new_count} new" if new_count > 0 else "no updates"
                print(f"  [{watch.state}] {watch.docket_number:<25} {status} (total: {len(filings)})")

                if not dry_run:
                    watch.last_checked_at = datetime.now(timezone.utc)
                    watch.filings_count = len(filings)
                    if filings and filings[0].filed_date:
                        watch.last_filing_date = datetime.combine(
                            max(f.filed_date for f in filings if f.filed_date),
                            datetime.min.time(),
                        ).replace(tzinfo=timezone.utc)

            except Exception as e:
                print(f"  [{watch.state}] {watch.docket_number:<25} ERROR: {e}")

        if not dry_run:
            session.commit()

    except Exception as e:
        logger.error(f"Watchlist check failed: {e}")
        raise
    finally:
        session.close()


def _save_dockets_to_db(dockets):
    """Save discovered dockets as Filing records."""
    from app.database import SessionLocal
    from app.models import Filing, Regulator

    session = SessionLocal()
    try:
        regulators = {r.state: r.id for r in session.query(Regulator).all()}
        created = 0

        for d in dockets:
            # Check if filing already exists
            existing = (
                session.query(Filing)
                .filter_by(docket_number=d.docket_number)
                .first()
            )
            if existing:
                continue

            # Need a utility_id - skip if we can't determine one
            # These are discovery records, utility matching happens later
            filing = Filing(
                utility_id=1,  # Placeholder, to be updated by matching
                regulator_id=regulators.get(d.source_url[:2] if d.source_url else None),
                docket_number=d.docket_number,
                filing_type=d.filing_type or "unknown",
                title=d.title,
                source_url=d.source_url,
                status="discovered",
            )
            session.add(filing)
            created += 1

        session.commit()
        logger.info(f"Saved {created} new docket records to DB")
    except Exception as e:
        session.rollback()
        logger.warning(f"DB save failed (non-critical): {e}")
    finally:
        session.close()


if __name__ == "__main__":
    main()
