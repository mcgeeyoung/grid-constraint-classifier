"""
Import Congestion Pipeline CLI.

Usage:
  python -m cli.ingest_congestion seed-bas
  python -m cli.ingest_congestion ingest-eia --ba BANC --start 2024-01-01 --end 2024-12-31
  python -m cli.ingest_congestion ingest-eia --ba all --since
  python -m cli.ingest_congestion estimate-limits
  python -m cli.ingest_congestion ingest-lmp --rto CAISO --year 2024
  python -m cli.ingest_congestion ingest-lmp --rto MISO --year 2024
  python -m cli.ingest_congestion ingest-lmp --rto SPP --year 2024
  python -m cli.ingest_congestion ingest-lmp --rto PJM --year 2024
  python -m cli.ingest_congestion compute-scores --year 2024 --period-type year
"""

import argparse
import json
import logging
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def cmd_seed_bas(args):
    """Load BA reference data from JSON into balancing_authorities table."""
    from app.database import SessionLocal
    from app.models.congestion import BalancingAuthority

    ref_path = Path(__file__).resolve().parent.parent / "data" / "reference" / "ba_interface_map.json"
    if not ref_path.exists():
        logger.error(f"Reference file not found: {ref_path}")
        sys.exit(1)

    with open(ref_path) as f:
        ba_data = json.load(f)

    db = SessionLocal()
    try:
        created = 0
        updated = 0
        for entry in ba_data:
            existing = db.query(BalancingAuthority).filter_by(
                ba_code=entry["ba_code"]
            ).first()

            if existing:
                # Update existing record
                existing.ba_name = entry["ba_name"]
                existing.region = entry.get("region")
                existing.interconnection = entry.get("interconnection")
                existing.is_rto = entry.get("is_rto", False)
                existing.rto_neighbor = entry.get("rto_neighbor")
                existing.rto_neighbor_secondary = entry.get("rto_neighbor_secondary")
                existing.interface_points = entry.get("interface_points")
                existing.latitude = entry.get("latitude")
                existing.longitude = entry.get("longitude")
                updated += 1
            else:
                ba = BalancingAuthority(
                    ba_code=entry["ba_code"],
                    ba_name=entry["ba_name"],
                    region=entry.get("region"),
                    interconnection=entry.get("interconnection"),
                    is_rto=entry.get("is_rto", False),
                    rto_neighbor=entry.get("rto_neighbor"),
                    rto_neighbor_secondary=entry.get("rto_neighbor_secondary"),
                    interface_points=entry.get("interface_points"),
                    latitude=entry.get("latitude"),
                    longitude=entry.get("longitude"),
                )
                db.add(ba)
                created += 1

        db.commit()
        total = db.query(BalancingAuthority).count()
        logger.info(
            f"Seeded BAs: {created} created, {updated} updated, {total} total"
        )
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to seed BAs: {e}")
        sys.exit(1)
    finally:
        db.close()


def cmd_ingest_eia(args):
    """Fetch EIA-930 data and store in ba_hourly_data table."""
    from datetime import datetime, timedelta

    from app.config import settings
    from app.database import SessionLocal
    from app.models.congestion import BalancingAuthority, BAHourlyData
    from adapters.eia_client import EIAClient

    if not settings.EIA_API_KEY:
        logger.error("EIA_API_KEY not set. Add to .env file.")
        sys.exit(1)

    client = EIAClient(api_key=settings.EIA_API_KEY)
    db = SessionLocal()

    try:
        # Resolve BA list
        if args.ba == "all":
            bas = db.query(BalancingAuthority).filter_by(is_rto=False).all()
        else:
            ba = db.query(BalancingAuthority).filter_by(ba_code=args.ba).first()
            if not ba:
                logger.error(f"BA '{args.ba}' not found in database. Run seed-bas first.")
                sys.exit(1)
            bas = [ba]

        for ba in bas:
            # Determine date range
            if args.since:
                last_ts = (
                    db.query(BAHourlyData.timestamp_utc)
                    .filter_by(ba_id=ba.id)
                    .order_by(BAHourlyData.timestamp_utc.desc())
                    .first()
                )
                if last_ts:
                    start = (last_ts[0] + timedelta(hours=1)).strftime("%Y-%m-%dT%H")
                else:
                    start = args.start or "2024-01-01"
                end = args.end or datetime.utcnow().strftime("%Y-%m-%dT%H")
            else:
                start = args.start
                end = args.end

            if not start or not end:
                logger.error(f"Provide --start/--end or use --since for {ba.ba_code}")
                continue

            logger.info(f"Fetching EIA data for {ba.ba_code}: {start} to {end}")
            df = client.fetch_region_data(ba.ba_code, start, end)

            if df.empty:
                logger.warning(f"No data returned for {ba.ba_code}")
                continue

            # Upsert rows
            inserted = 0
            skipped = 0
            for _, row in df.iterrows():
                ts = row["timestamp_utc"].to_pydatetime().replace(tzinfo=None)
                existing = (
                    db.query(BAHourlyData)
                    .filter_by(ba_id=ba.id, timestamp_utc=ts)
                    .first()
                )
                if existing:
                    skipped += 1
                    continue

                record = BAHourlyData(
                    ba_id=ba.id,
                    timestamp_utc=ts,
                    demand_mw=row.get("demand_mw"),
                    net_generation_mw=row.get("net_generation_mw"),
                    total_interchange_mw=row.get("total_interchange_mw"),
                    net_imports_mw=row.get("net_imports_mw"),
                )
                db.add(record)
                inserted += 1

                # Commit in batches
                if inserted % 1000 == 0:
                    db.commit()

            db.commit()
            logger.info(
                f"{ba.ba_code}: {inserted} inserted, {skipped} skipped"
            )

    except Exception as e:
        db.rollback()
        logger.error(f"Ingestion failed: {e}")
        raise
    finally:
        db.close()


def cmd_estimate_limits(args):
    """Estimate transfer limits as 99th percentile of net imports."""
    import numpy as np

    from app.database import SessionLocal
    from app.models.congestion import BalancingAuthority, BAHourlyData

    db = SessionLocal()
    try:
        bas = db.query(BalancingAuthority).filter_by(is_rto=False).all()
        updated = 0
        for ba in bas:
            imports = (
                db.query(BAHourlyData.net_imports_mw)
                .filter_by(ba_id=ba.id)
                .filter(BAHourlyData.net_imports_mw.isnot(None))
                .all()
            )
            if not imports:
                logger.warning(f"{ba.ba_code}: no hourly data, skipping")
                continue

            values = [row[0] for row in imports if row[0] is not None and not np.isnan(row[0])]
            if not values:
                logger.warning(f"{ba.ba_code}: all import values are null, skipping")
                continue
            p99 = float(np.percentile(values, 99))
            ba.transfer_limit_mw = p99
            ba.transfer_limit_method = "p99"
            updated += 1
            logger.info(f"{ba.ba_code}: P99 transfer limit = {p99:.0f} MW")

        db.commit()
        logger.info(f"Updated transfer limits for {updated} BAs")
    finally:
        db.close()


def cmd_ingest_lmp(args):
    """Fetch interface LMP data via gridstatus and store in interface_lmps table.

    Supports CAISO, MISO, SPP, and PJM.
    """
    from datetime import date

    from app.database import SessionLocal
    from app.models.congestion import BalancingAuthority, InterfaceLMP
    from adapters.congestion_lmp import GridStatusLMPAdapter, RTO_CONFIG

    rto = args.rto.upper()
    year = args.year

    if rto not in RTO_CONFIG:
        logger.error(f"Unsupported RTO: {rto}. Supported: {list(RTO_CONFIG)}")
        sys.exit(1)

    if RTO_CONFIG[rto].get("disabled"):
        logger.error(f"{rto} is currently disabled: historical DA LMP downloads are unavailable.")
        sys.exit(1)

    adapter = GridStatusLMPAdapter(rto=rto)
    db = SessionLocal()

    start_date = date(year, 1, 1)
    end_date = date(year + 1, 1, 1)

    try:
        # Collect unique node IDs for this RTO from BA interface_points
        # Match both rto_neighbor and rto_neighbor_secondary
        bas = db.query(BalancingAuthority).filter(
            (BalancingAuthority.rto_neighbor == rto) |
            (BalancingAuthority.rto_neighbor_secondary == rto)
        ).all()

        node_ids = set()
        for ba in bas:
            if not ba.interface_points:
                continue
            for pt in ba.interface_points:
                if pt.get("rto") == rto and pt.get("gridstatus_verified", False):
                    node_ids.add(pt["node_id"])

        # Allow --node override
        if args.node:
            node_ids = {args.node}

        if not node_ids:
            logger.error(f"No interface nodes found for {rto}.")
            sys.exit(1)

        config = RTO_CONFIG[rto]
        hub_names = list(config["hubs"].keys())
        logger.info(
            f"Fetching LMP for {len(node_ids)} {rto} interface nodes "
            f"+ {len(hub_names)} hub baselines"
        )

        # Fetch interface node LMPs
        for node_id in sorted(node_ids):
            logger.info(f"=== {rto}/{node_id} ===")
            df = adapter.fetch_node_lmp(node_id, start_date, end_date)

            if df.empty:
                logger.warning(f"No LMP data for {node_id}")
                continue

            inserted = _upsert_lmp_rows(db, rto, df)
            logger.info(f"{node_id}: {inserted} rows inserted ({len(df)} fetched)")

        # Fetch hub baselines
        for hub in hub_names:
            logger.info(f"=== {rto} {hub} baseline ===")
            df = adapter.fetch_hub_baseline(start_date, end_date, hub=hub)

            if df.empty:
                logger.warning(f"No baseline LMP data for {rto}/{hub}")
                continue

            inserted = _upsert_lmp_rows(db, rto, df)
            logger.info(f"{rto}_{hub}_BASELINE: {inserted} rows inserted ({len(df)} fetched)")

        total = db.query(InterfaceLMP).filter_by(rto=rto).count()
        logger.info(f"Total {rto} LMP rows in DB: {total}")

    except Exception as e:
        db.rollback()
        logger.error(f"LMP ingestion failed: {e}")
        raise
    finally:
        db.close()


def _upsert_lmp_rows(db, rto: str, df) -> int:
    """Insert LMP rows, skipping duplicates. Returns count inserted."""
    from app.models.congestion import InterfaceLMP

    inserted = 0
    for _, row in df.iterrows():
        ts = row["timestamp_utc"]
        if hasattr(ts, "to_pydatetime"):
            ts = ts.to_pydatetime()
        ts = ts.replace(tzinfo=None)

        existing = (
            db.query(InterfaceLMP.id)
            .filter_by(rto=rto, node_id=row["node_id"], timestamp_utc=ts)
            .first()
        )
        if existing:
            continue

        record = InterfaceLMP(
            rto=rto,
            node_id=row["node_id"],
            timestamp_utc=ts,
            lmp=row.get("lmp"),
            energy_component=row.get("energy_component"),
            congestion_component=row.get("congestion_component"),
            loss_component=row.get("loss_component"),
            market_type="DA",
        )
        db.add(record)
        inserted += 1

        if inserted % 1000 == 0:
            db.commit()

    db.commit()
    return inserted


def cmd_compute_scores(args):
    """Compute congestion scores for all BAs."""
    import calendar
    from datetime import date

    import pandas as pd

    from app.database import SessionLocal
    from app.models.congestion import BalancingAuthority, BAHourlyData, CongestionScore, InterfaceLMP
    from core.congestion_calculator import compute_congestion_metrics

    year = args.year
    period_type = args.period_type

    db = SessionLocal()
    try:
        bas = db.query(BalancingAuthority).filter_by(is_rto=False).all()
        computed = 0
        skipped = 0
        lmp_enriched = 0

        for ba in bas:
            if period_type == "year":
                periods = [(date(year, 1, 1), date(year, 12, 31))]
            else:
                periods = []
                for m in range(1, 13):
                    last_day = calendar.monthrange(year, m)[1]
                    periods.append((date(year, m, 1), date(year, m, last_day)))

            # Resolve interface node IDs and baseline node for this BA
            interface_node_ids, baseline_node_id = _resolve_lmp_nodes(ba)

            for p_start, p_end in periods:
                # Fetch hourly data for this period
                hourly = (
                    db.query(BAHourlyData)
                    .filter(
                        BAHourlyData.ba_id == ba.id,
                        BAHourlyData.timestamp_utc >= str(p_start),
                        BAHourlyData.timestamp_utc <= str(p_end) + "T23:59:59",
                    )
                    .all()
                )

                if not hourly:
                    skipped += 1
                    continue

                df = pd.DataFrame([{
                    "timestamp_utc": h.timestamp_utc,
                    "demand_mw": h.demand_mw,
                    "net_generation_mw": h.net_generation_mw,
                    "total_interchange_mw": h.total_interchange_mw,
                    "net_imports_mw": h.net_imports_mw,
                } for h in hourly])

                tl = ba.transfer_limit_mw
                if not tl or tl <= 0:
                    skipped += 1
                    continue

                # Fetch interface LMP data if nodes are mapped
                interface_lmp_df = None
                baseline_lmp_df = None

                if interface_node_ids:
                    interface_lmp_df = _fetch_lmp_df(
                        db, interface_node_ids, p_start, p_end
                    )
                    if baseline_node_id:
                        baseline_lmp_df = _fetch_lmp_df(
                            db, [baseline_node_id], p_start, p_end
                        )

                metrics = compute_congestion_metrics(
                    df, tl, p_start, p_end, period_type,
                    interface_lmp_df=interface_lmp_df,
                    baseline_lmp_df=baseline_lmp_df,
                )

                if interface_lmp_df is not None and not interface_lmp_df.empty:
                    lmp_enriched += 1

                # Upsert score
                existing = (
                    db.query(CongestionScore)
                    .filter_by(ba_id=ba.id, period_start=p_start, period_type=period_type)
                    .first()
                )
                if existing:
                    for key, val in metrics.items():
                        if key not in ("period_start", "period_end", "period_type"):
                            setattr(existing, key, val)
                else:
                    score = CongestionScore(ba_id=ba.id, **metrics)
                    db.add(score)

                computed += 1

            db.commit()

        logger.info(
            f"Computed {computed} scores ({lmp_enriched} with LMP data), "
            f"{skipped} skipped (no data or no transfer limit)"
        )
    except Exception as e:
        db.rollback()
        logger.error(f"Score computation failed: {e}")
        raise
    finally:
        db.close()


def _resolve_lmp_nodes(ba):
    """Extract interface node IDs and baseline node ID from a BA's interface_points.

    Returns (list[str], str|None) - interface node IDs and baseline node ID.

    Baseline selection per RTO:
    - CAISO: NP15 for Northern CA/NW, SP15 for Southern CA/SW
    - MISO: Indiana Hub (most liquid MISO hub)
    - SPP: South Hub
    - PJM: Western Hub (most liquid PJM hub)
    """
    if not ba.interface_points:
        return [], None

    # Use primary RTO neighbor for scoring (avoids mixing MISO+PJM for dual-RTO BAs)
    primary_rto = ba.rto_neighbor

    node_ids = []
    for pt in ba.interface_points:
        if pt.get("rto") == primary_rto and pt.get("gridstatus_verified", False):
            node_ids.append(pt["node_id"])

    if not node_ids:
        return [], None

    # Determine baseline hub based on primary RTO neighbor
    baseline_node_id = None
    if primary_rto == "CAISO":
        northern_nodes = {"MALIN_5_N101", "CAPTJACK_5_N101", "NOB_5_N101"}
        if any(n in northern_nodes for n in node_ids):
            baseline_node_id = "CAISO_NP15_BASELINE"
        else:
            baseline_node_id = "CAISO_SP15_BASELINE"
    elif primary_rto == "MISO":
        baseline_node_id = "MISO_INDIANA_BASELINE"
    elif primary_rto == "SPP":
        baseline_node_id = "SPP_SOUTH_BASELINE"
    elif primary_rto == "PJM":
        baseline_node_id = "PJM_WESTERN_BASELINE"

    return node_ids, baseline_node_id


def _fetch_lmp_df(db, node_ids, p_start, p_end):
    """Fetch LMP data from interface_lmps table for given nodes and period.

    If multiple nodes, averages their LMP (weighted equally) per timestamp.
    Returns DataFrame with columns [timestamp_utc, lmp].
    """
    import pandas as pd
    from app.models.congestion import InterfaceLMP

    rows = (
        db.query(
            InterfaceLMP.timestamp_utc,
            InterfaceLMP.lmp,
        )
        .filter(
            InterfaceLMP.node_id.in_(node_ids),
            InterfaceLMP.timestamp_utc >= str(p_start),
            InterfaceLMP.timestamp_utc <= str(p_end) + "T23:59:59",
        )
        .all()
    )

    if not rows:
        return None

    df = pd.DataFrame(rows, columns=["timestamp_utc", "lmp"])

    # Average across nodes if multiple (e.g., BANC has MALIN + CAPTJACK)
    if len(node_ids) > 1:
        df = df.groupby("timestamp_utc", as_index=False)["lmp"].mean()

    return df


def main():
    parser = argparse.ArgumentParser(
        description="Import Congestion Pipeline CLI",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # seed-bas
    sub_seed = subparsers.add_parser(
        "seed-bas",
        help="Seed balancing_authorities from reference JSON",
    )

    # ingest-eia
    sub_ingest = subparsers.add_parser(
        "ingest-eia",
        help="Fetch EIA-930 data into ba_hourly_data",
    )
    sub_ingest.add_argument(
        "--ba", required=True,
        help="BA code (e.g., BANC) or 'all'",
    )
    sub_ingest.add_argument("--start", help="Start date (YYYY-MM-DD)")
    sub_ingest.add_argument("--end", help="End date (YYYY-MM-DD)")
    sub_ingest.add_argument(
        "--since", action="store_true",
        help="Incremental: start from last timestamp in DB",
    )

    # ingest-lmp
    sub_lmp = subparsers.add_parser(
        "ingest-lmp",
        help="Fetch interface LMP data into interface_lmps (CAISO, MISO, SPP, PJM)",
    )
    sub_lmp.add_argument(
        "--rto", required=True,
        help="RTO to fetch LMP for (CAISO, MISO, SPP, PJM)",
    )
    sub_lmp.add_argument(
        "--year", type=int, required=True,
        help="Year to backfill",
    )
    sub_lmp.add_argument(
        "--node",
        help="Specific node ID (default: all verified nodes for the RTO)",
    )

    # estimate-limits
    sub_limits = subparsers.add_parser(
        "estimate-limits",
        help="Compute P99 transfer limits from hourly data",
    )

    # compute-scores
    sub_scores = subparsers.add_parser(
        "compute-scores",
        help="Compute congestion scores (requires hourly data)",
    )
    sub_scores.add_argument("--year", type=int, help="Year to compute")
    sub_scores.add_argument(
        "--period-type", choices=["month", "year"], default="year",
    )

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    commands = {
        "seed-bas": cmd_seed_bas,
        "ingest-eia": cmd_ingest_eia,
        "ingest-lmp": cmd_ingest_lmp,
        "estimate-limits": cmd_estimate_limits,
        "compute-scores": cmd_compute_scores,
    }
    commands[args.command](args)


if __name__ == "__main__":
    main()
