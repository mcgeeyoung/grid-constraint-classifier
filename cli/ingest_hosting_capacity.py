"""
Utility Hosting Capacity Ingestion CLI.

Usage:
  python -m cli.ingest_hosting_capacity --utility pge
  python -m cli.ingest_hosting_capacity --utility all
  python -m cli.ingest_hosting_capacity --utility all --category arcgis_feature
  python -m cli.ingest_hosting_capacity --utility pge --force
  python -m cli.ingest_hosting_capacity --utility pge --dry-run
  python -m cli.ingest_hosting_capacity --list-utilities
  python -m cli.ingest_hosting_capacity --utility pge --discover
"""

import argparse
import logging
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from adapters.arcgis_client import ArcGISClient
from adapters.hosting_capacity.base import UtilityHCConfig
from adapters.hosting_capacity.registry import get_hc_adapter, list_hc_utilities

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(
        description="Ingest utility hosting capacity data",
    )
    parser.add_argument("--utility", help="Utility code or 'all'")
    parser.add_argument(
        "--force", action="store_true", help="Force re-download (ignore cache)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Fetch + normalize only, no DB write",
    )
    parser.add_argument(
        "--list-utilities", action="store_true",
        help="List all configured utilities",
    )
    parser.add_argument(
        "--discover", action="store_true",
        help="Discover layers and fields for a utility",
    )
    parser.add_argument(
        "--category", help="Filter by data_source_type (e.g. arcgis_feature)",
    )
    parser.add_argument(
        "--data-dir", default="data", type=Path,
        help="Base data directory (default: data)",
    )
    args = parser.parse_args()

    if args.list_utilities:
        _print_utility_list()
        return

    if not args.utility:
        parser.error("--utility is required (or use --list-utilities)")

    if args.discover:
        _discover_utility(args.utility)
        return

    if args.utility == "all":
        utilities = list_hc_utilities()
        if args.category:
            configs_dir = Path(__file__).resolve().parent.parent / "adapters" / "hosting_capacity" / "configs"
            filtered = []
            for code in utilities:
                cfg = UtilityHCConfig.from_yaml(configs_dir / f"{code}.yaml")
                if cfg.data_source_type == args.category:
                    filtered.append(code)
            utilities = filtered
            logger.info(f"Filtered to {len(utilities)} utilities with category={args.category}")

        results = {}
        for code in utilities:
            results[code] = _ingest_single(code, args)

        # Print summary table
        print(f"\n{'='*60}")
        print(f"{'Utility':<12} {'Records':>8} {'Status':<12}")
        print(f"{'-'*60}")
        for code, result in results.items():
            print(f"{code:<12} {result['records']:>8} {result['status']:<12}")
        print(f"{'='*60}")

        total = sum(r["records"] for r in results.values())
        ok = sum(1 for r in results.values() if r["status"] in ("completed", "dry_run"))
        print(f"Total: {total} records across {ok}/{len(results)} utilities\n")
    else:
        _ingest_single(args.utility, args)


def _ingest_single(utility_code: str, args) -> dict:
    """Ingest hosting capacity data for a single utility."""
    try:
        adapter = get_hc_adapter(utility_code, data_dir=args.data_dir)
    except FileNotFoundError as e:
        logger.error(str(e))
        return {"records": 0, "status": "not_configured"}

    logger.info(
        f"=== Ingesting {adapter.config.utility_name} ({utility_code}) ==="
    )

    # Fetch + normalize
    try:
        df = adapter.pull_hosting_capacity(force=args.force)
    except Exception as e:
        logger.error(f"Fetch failed for {utility_code}: {e}")
        return {"records": 0, "status": "fetch_failed", "error": str(e)}

    logger.info(f"Fetched {len(df)} records for {utility_code}")

    if df.empty:
        return {"records": 0, "status": "empty"}

    if args.dry_run:
        _print_sample(df, utility_code)
        return {"records": len(df), "status": "dry_run"}

    # DB write
    from app.hc_writer import HostingCapacityWriter

    writer = HostingCapacityWriter()
    run = None
    try:
        utility = writer.ensure_utility(adapter.config)
        run = writer.start_run(utility, adapter.resolve_current_url())
        run.records_fetched = len(df)

        count = writer.write_records(df, utility, run)
        writer.compute_summary(utility)
        writer.complete_run(run)

        logger.info(f"Wrote {count} records to DB for {utility_code}")
        return {"records": count, "status": "completed"}
    except Exception as e:
        logger.error(f"Ingestion failed for {utility_code}: {e}")
        if run:
            writer.complete_run(run, error=str(e))
        return {"records": 0, "status": "failed", "error": str(e)}
    finally:
        writer.close()


def _print_utility_list():
    """Print a table of all configured utilities."""
    configs_dir = (
        Path(__file__).resolve().parent.parent
        / "adapters" / "hosting_capacity" / "configs"
    )
    codes = list_hc_utilities()

    print(f"\n{'Code':<12} {'Name':<30} {'Type':<16} {'ISO':<8} {'States'}")
    print("-" * 80)
    for code in codes:
        cfg = UtilityHCConfig.from_yaml(configs_dir / f"{code}.yaml")
        states = ", ".join(cfg.states) if cfg.states else ""
        print(
            f"{cfg.utility_code:<12} {cfg.utility_name:<30} "
            f"{cfg.data_source_type:<16} {cfg.iso_id:<8} {states}"
        )
    print(f"\nTotal: {len(codes)} utilities configured\n")


def _discover_utility(utility_code: str):
    """Discover layers and fields for a utility's ArcGIS endpoint."""
    configs_dir = (
        Path(__file__).resolve().parent.parent
        / "adapters" / "hosting_capacity" / "configs"
    )
    config_path = configs_dir / f"{utility_code}.yaml"
    if not config_path.exists():
        logger.error(f"No config for '{utility_code}'")
        return

    config = UtilityHCConfig.from_yaml(config_path)
    if not config.service_url:
        logger.error(f"{utility_code}: no service_url configured")
        return

    client = ArcGISClient()

    # Discover layers
    print(f"\n=== {config.utility_name} ({config.service_url}) ===\n")
    layers = client.discover_layers(config.service_url)
    if layers:
        print(f"{'ID':>4}  {'Type':<6}  Name")
        print("-" * 50)
        for layer in layers:
            marker = " <--" if layer["id"] == config.layer_index else ""
            print(f"{layer['id']:>4}  {layer['type']:<6}  {layer['name']}{marker}")

    # Get field schema for configured layer
    if config.layer_index is not None:
        layer_url = f"{config.service_url}/{config.layer_index}"
        fields = client.get_field_schema(layer_url)
        count = client.get_record_count(f"{layer_url}/query")

        print(f"\n--- Layer {config.layer_index} fields ({count} records) ---\n")
        print(f"{'Field':<35} {'Type':<15} {'Alias'}")
        print("-" * 70)
        for f in fields:
            mapped = config.field_map.get(f["name"], "")
            marker = f" -> {mapped}" if mapped else ""
            print(
                f"{f['name']:<35} {f.get('type', '?'):<15} "
                f"{f.get('alias', '')}{marker}"
            )

    print()


def _print_sample(df, utility_code: str):
    """Print sample data and stats for dry-run mode."""
    print(f"\n--- {utility_code}: {len(df)} records (dry run) ---\n")

    # Stats
    canonical_cols = [
        "hosting_capacity_mw", "installed_dg_mw", "remaining_capacity_mw",
    ]
    for col in canonical_cols:
        if col in df.columns and not df[col].isna().all():
            print(
                f"  {col}: min={df[col].min():.2f}, "
                f"max={df[col].max():.2f}, "
                f"mean={df[col].mean():.2f}"
            )

    if "constraining_metric" in df.columns:
        counts = df["constraining_metric"].value_counts().head(5)
        print(f"\n  Top constraints:")
        for name, ct in counts.items():
            print(f"    {name}: {ct}")

    if "centroid_lat" in df.columns:
        non_null = df["centroid_lat"].notna().sum()
        print(f"\n  Geometry: {non_null}/{len(df)} records have centroids")

    # Sample rows
    sample_cols = [
        c for c in ["feeder_id_external", "hosting_capacity_mw",
                     "remaining_capacity_mw", "constraining_metric"]
        if c in df.columns
    ]
    if sample_cols:
        print(f"\n  Sample (first 5 rows):")
        print(df[sample_cols].head().to_string(index=False))

    print()


if __name__ == "__main__":
    main()
