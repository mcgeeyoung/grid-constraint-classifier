"""Document Parsing & LLM Extraction CLI.

Parses regulatory filing documents (PDFs, Excel files) and optionally
runs LLM-assisted extraction to produce structured data (load forecasts,
grid constraints, resource needs, hosting capacity).

Usage:
  python -m cli.parse_documents --file path/to/filing.pdf
  python -m cli.parse_documents --file path/to/data.xlsx --utility "PG&E"
  python -m cli.parse_documents --file path/to/irp.pdf --llm --extract load_forecast
  python -m cli.parse_documents --file path/to/gna.pdf --llm --extract grid_constraint
  python -m cli.parse_documents --dir data/puc_documents/CA/ --utility "PG&E"
  python -m cli.parse_documents --file path/to/doc.pdf --triage-only
  python -m cli.parse_documents --file path/to/doc.pdf --llm --save-to-db
"""

import argparse
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from adapters.document_parser.pipeline import parse_document
from adapters.document_parser.base import DocumentParseResult

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="Parse regulatory filing documents")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--file", type=Path, help="Single file to parse")
    source.add_argument("--dir", type=Path, help="Directory of files to parse")

    parser.add_argument("--utility", help="Utility name for LLM context")
    parser.add_argument("--filing-type", help="Filing type (IRP, DRP, GNA, rate_case)")
    parser.add_argument("--llm", action="store_true", help="Run LLM extraction")
    parser.add_argument(
        "--extract", action="append",
        help="Extraction type(s): load_forecast, grid_constraint, resource_need, "
             "hosting_capacity, general_summary (repeatable)",
    )
    parser.add_argument("--max-pages", type=int, help="Max PDF pages to process")
    parser.add_argument("--triage-only", action="store_true", help="Only classify, don't parse")
    parser.add_argument("--save-to-db", action="store_true", help="Save extractions to database")
    parser.add_argument("--output-json", type=Path, help="Save results to JSON file")

    args = parser.parse_args()

    if args.file:
        files = [args.file]
    else:
        extensions = {".pdf", ".xlsx", ".xls", ".csv"}
        files = sorted(
            f for f in args.dir.rglob("*")
            if f.suffix.lower() in extensions
        )
        logger.info(f"Found {len(files)} documents in {args.dir}")

    if not files:
        logger.error("No files to process")
        return

    results = []
    for file_path in files:
        logger.info(f"\n{'='*60}")
        logger.info(f"Processing: {file_path.name}")

        if args.triage_only:
            result = _triage_only(file_path, args.filing_type)
        else:
            result = parse_document(
                file_path=file_path,
                utility_name=args.utility,
                filing_type=args.filing_type,
                run_llm=args.llm,
                llm_extraction_types=args.extract,
                max_pages=args.max_pages,
            )

        _print_result(result)
        results.append(result)

    # Summary
    if len(results) > 1:
        _print_summary(results)

    # Save results
    if args.output_json:
        _save_json(results, args.output_json)

    if args.save_to_db and any(r.has_extractions for r in results):
        _save_to_db(results, args.utility)


def _triage_only(file_path: Path, filing_type: str = None) -> DocumentParseResult:
    """Quick triage without full parsing."""
    from adapters.document_parser.triage import classify_document, estimate_relevance
    from adapters.document_parser.pdf_parser import extract_text
    from adapters.document_parser.base import DocumentParseResult

    result = DocumentParseResult(file_path=str(file_path))

    # Extract first few pages of text for triage
    text = ""
    page_count = None
    if file_path.suffix.lower() == ".pdf":
        text, page_count = extract_text(file_path, max_pages=3)
        result.page_count = page_count
        result.text_length = len(text)

    result.category = classify_document(file_path, text[:2000] if text else None, page_count)
    result.status = "triaged"

    return result


def _print_result(result: DocumentParseResult):
    """Print parsing results for a single document."""
    name = Path(result.file_path).name
    print(f"\n--- {name} ---")
    print(f"  Category: {result.category.value}")
    print(f"  Status: {result.status}")

    if result.page_count:
        print(f"  Pages: {result.page_count}")
    if result.text_length:
        print(f"  Text length: {result.text_length:,} chars")

    if result.tables:
        print(f"  Tables extracted: {len(result.tables)}")
        for i, table in enumerate(result.tables):
            title = table.title or f"table_{i}"
            print(f"    [{i}] {title}: {len(table.df)} rows x {len(table.df.columns)} cols "
                  f"({table.confidence.value}, {table.source_method})")

    if result.extractions:
        print(f"  LLM extractions: {len(result.extractions)}")
        for ext in result.extractions:
            print(f"    - {ext.extraction_type.value}: "
                  f"confidence={ext.confidence.value}")
            # Print key stats from the extraction
            _print_extraction_summary(ext)

    if result.errors:
        print(f"  Errors: {'; '.join(result.errors)}")

    if result.needs_review:
        print(f"  ** NEEDS REVIEW (low confidence extractions)")


def _print_extraction_summary(ext):
    """Print a brief summary of extracted data."""
    data = ext.data
    etype = ext.extraction_type.value

    if etype == "load_forecast":
        scenarios = data.get("scenarios", [])
        for s in scenarios:
            years = [d.get("year") for d in s.get("data", []) if d.get("year")]
            if years:
                print(f"      {s.get('name', '?')}: {min(years)}-{max(years)} "
                      f"({len(s.get('data', []))} data points)")

    elif etype == "grid_constraint":
        constraints = data.get("constraints", [])
        print(f"      {len(constraints)} constraints found")
        for c in constraints[:3]:
            print(f"        {c.get('location_name', '?')}: "
                  f"{c.get('constraint_type', '?')}")

    elif etype == "resource_need":
        needs = data.get("needs", [])
        total_mw = sum(n.get("need_mw", 0) or 0 for n in needs)
        print(f"      {len(needs)} needs, {total_mw:,.0f} MW total")

    elif etype == "hosting_capacity":
        records = data.get("records", [])
        print(f"      {len(records)} feeder records")

    elif etype == "general_summary":
        findings = data.get("key_findings", [])
        for f in findings[:3]:
            print(f"      - {f[:80]}")


def _print_summary(results: list[DocumentParseResult]):
    """Print summary across all processed documents."""
    print(f"\n{'='*60}")
    print(f"Summary: {len(results)} documents processed\n")

    by_category = {}
    for r in results:
        by_category.setdefault(r.category.value, []).append(r)

    print(f"{'Category':<20} {'Count':>5} {'Tables':>7} {'LLM':>5} {'Review':>7}")
    print("-" * 50)
    for cat, docs in sorted(by_category.items()):
        tables = sum(len(d.tables) for d in docs)
        llm = sum(len(d.extractions) for d in docs)
        review = sum(1 for d in docs if d.needs_review)
        print(f"{cat:<20} {len(docs):>5} {tables:>7} {llm:>5} {review:>7}")

    total_tables = sum(len(r.tables) for r in results)
    total_extractions = sum(len(r.extractions) for r in results)
    total_review = sum(1 for r in results if r.needs_review)
    print(f"\nTotals: {total_tables} tables, {total_extractions} LLM extractions, "
          f"{total_review} needing review\n")


def _save_json(results: list[DocumentParseResult], output_path: Path):
    """Save results to JSON file."""
    output = []
    for r in results:
        entry = {
            "file": r.file_path,
            "category": r.category.value,
            "status": r.status,
            "page_count": r.page_count,
            "tables_count": len(r.tables),
            "extractions": [],
            "errors": r.errors,
        }
        for ext in r.extractions:
            entry["extractions"].append({
                "type": ext.extraction_type.value,
                "confidence": ext.confidence.value,
                "data": ext.data,
                "model": ext.llm_model,
            })
        output.append(entry)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2, default=str)

    logger.info(f"Results saved to {output_path}")


def _save_to_db(results: list[DocumentParseResult], utility_name: str = None):
    """Save LLM extractions to the database as structured records."""
    from app.database import SessionLocal
    from app.models import GridConstraint, LoadForecast, ResourceNeed, Utility

    session = SessionLocal()
    try:
        # Find utility
        utility = None
        if utility_name:
            utility = (
                session.query(Utility)
                .filter(Utility.utility_name.ilike(f"%{utility_name}%"))
                .first()
            )

        saved = 0
        for result in results:
            for ext in result.extractions:
                if ext.confidence.value == "low":
                    logger.info(f"Skipping low-confidence {ext.extraction_type.value}")
                    continue

                try:
                    saved += _save_extraction(session, ext, utility)
                except Exception as e:
                    logger.warning(f"Failed to save {ext.extraction_type.value}: {e}")

        session.commit()
        logger.info(f"Saved {saved} records to DB")

    except Exception as e:
        session.rollback()
        logger.error(f"DB save failed: {e}")
    finally:
        session.close()


def _save_extraction(session, ext, utility) -> int:
    """Save a single extraction to the appropriate DB table. Returns count saved."""
    from app.models import GridConstraint, LoadForecast, ResourceNeed

    utility_id = utility.id if utility else None
    count = 0

    if ext.extraction_type.value == "load_forecast" and utility_id:
        for scenario in ext.data.get("scenarios", []):
            for dp in scenario.get("data", []):
                lf = LoadForecast(
                    utility_id=utility_id,
                    forecast_year=dp.get("year", 0),
                    area_name=ext.data.get("area_name"),
                    area_type=ext.data.get("area_type"),
                    peak_demand_mw=dp.get("peak_demand_mw"),
                    energy_gwh=dp.get("energy_gwh"),
                    growth_rate_pct=dp.get("growth_rate_pct"),
                    scenario=scenario.get("name"),
                )
                session.add(lf)
                count += 1

    elif ext.extraction_type.value == "grid_constraint" and utility_id:
        for c in ext.data.get("constraints", []):
            gc = GridConstraint(
                utility_id=utility_id,
                constraint_type=c.get("constraint_type", "unknown"),
                location_type=c.get("location_type"),
                location_name=c.get("location_name"),
                current_capacity_mw=c.get("current_capacity_mw"),
                forecasted_load_mw=c.get("forecasted_load_mw"),
                headroom_mw=c.get("headroom_mw"),
                constraint_year=c.get("constraint_year"),
                confidence=ext.confidence.value,
                notes=c.get("notes"),
                raw_source_reference=c.get("proposed_solution"),
            )
            session.add(gc)
            count += 1

    elif ext.extraction_type.value == "resource_need" and utility_id:
        for n in ext.data.get("needs", []):
            rn = ResourceNeed(
                utility_id=utility_id,
                need_type=n.get("need_type", "unknown"),
                need_mw=n.get("need_mw"),
                need_year=n.get("need_year"),
                location_type=n.get("location_type"),
                location_name=n.get("location_name"),
                eligible_resource_types=n.get("eligible_resource_types"),
                notes=n.get("notes"),
            )
            session.add(rn)
            count += 1

    return count


if __name__ == "__main__":
    main()
