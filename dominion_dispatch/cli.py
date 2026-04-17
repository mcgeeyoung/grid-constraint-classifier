#!/usr/bin/env python3
"""
CLI entrypoints for Dominion DA congestion pulls (run from repo root).

  PYTHONPATH=. python -m dominion_dispatch.cli fetch-dom \\
      --date 2026-04-15 --output /tmp/dom_da_nodes.parquet

  PYTHONPATH=. python -m dominion_dispatch.cli dispatch-schedule \\
      --hourly-parquet /tmp/dom_da_nodes.parquet --devices-json devices.json \\
      --output /tmp/dispatch.parquet

  PYTHONPATH=. python -m dominion_dispatch.cli dispatch-schedule \\
      --hourly-from-run 42 --devices-from-db --persist

  PYTHONPATH=. python -m dominion_dispatch.cli asset-map \\
      --devices-json devices.json --output-html dom_assets.html \\
      --pull-pnode-definitions --geocode-pnodes

Requires ``PJM_SUBSCRIPTION_KEY`` for fetch/ingest and optional pnode list;
``DATABASE_URL`` for DB-backed CLI paths. Settlement zone for the program is **DOM** only.
"""

from __future__ import annotations

import argparse
from typing import Optional, Set
import json
import logging
import os
import sys
from datetime import date, datetime
from pathlib import Path

# Repo root on path when run as ``python -m dominion_dispatch.cli``
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from dominion_dispatch.da_congestion import fetch_da_node_congestion_dom
from dominion_dispatch.signals import build_device_da_congestion
from dominion_dispatch.config import (
    DEFAULT_DA_NODE_LMP_TYPE,
    DISPATCH_EXTREME_ABS_QUANTILE_DEFAULT,
    DISPATCH_STRESSED_ABS_USD_DEFAULT,
    DISPATCH_STRESSED_SIGNAL_FRACTION_DEFAULT,
    PJM_ZONE_DOM,
)
from dominion_dispatch.persist import ingest_da_dom_dataframe
from dominion_dispatch.dispatch_schedule import build_dispatch_schedule
from dominion_dispatch.persist_schedule import (
    fetch_active_devices_for_schedule,
    fetch_hourly_dataframe_for_run,
    persist_dispatch_schedule,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def _parse_date(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def _parse_peak_hours_ept(s: str) -> Set[int]:
    """Parse ``7,8,...,22`` into a set of integer hours 0–23 (EPT)."""
    out: set[int] = set()
    for part in s.split(","):
        part = part.strip()
        if not part:
            continue
        h = int(part)
        if h < 0 or h > 23:
            raise ValueError(f"peak hour must be 0-23, got {h}")
        out.add(h)
    if not out:
        raise ValueError("peak hours list is empty")
    return out


def cmd_ingest_dom(args: argparse.Namespace) -> int:
    key = os.environ.get("PJM_SUBSCRIPTION_KEY", "")
    if not key:
        logger.error("Set PJM_SUBSCRIPTION_KEY")
        return 1
    from src.pjm_client import PJMClient
    from app.database import SessionLocal

    day = _parse_date(args.date)
    z = args.zone or PJM_ZONE_DOM
    if z != PJM_ZONE_DOM:
        logger.warning("Dominion program targets %s; ingest zone is %s", PJM_ZONE_DOM, z)
    client = PJMClient(key)
    df = fetch_da_node_congestion_dom(
        client,
        day,
        lmp_type=args.lmp_type,
        zone=z,
    )
    db = SessionLocal()
    run = None
    try:
        run = ingest_da_dom_dataframe(
            db,
            df,
            day,
            zone_code=z,
            lmp_type=args.lmp_type,
            replace_existing=args.replace_existing,
        )
        db.commit()
        logger.info(
            "Ingestion run id=%s status=%s rows=%s retrieved_at=%s",
            run.id,
            run.status,
            run.row_count,
            run.retrieved_at_utc,
        )
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
    if run is None:
        return 1
    return 0 if run.status == "success" else 1


def cmd_fetch_dom(args: argparse.Namespace) -> int:
    key = os.environ.get("PJM_SUBSCRIPTION_KEY", "")
    if not key:
        logger.error("Set PJM_SUBSCRIPTION_KEY")
        return 1
    from src.pjm_client import PJMClient

    z = args.zone or PJM_ZONE_DOM
    if z != PJM_ZONE_DOM:
        logger.warning("Dominion program targets %s; fetch zone is %s", PJM_ZONE_DOM, z)
    client = PJMClient(key)
    day = _parse_date(args.date)
    end = _parse_date(args.end_date) if args.end_date else None
    df = fetch_da_node_congestion_dom(
        client,
        day,
        operating_day_end=end,
        lmp_type=args.lmp_type,
        zone=z,
    )
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out, index=False)
    logger.info("Wrote %s rows to %s", len(df), out)
    return 0


def cmd_dispatch_schedule(args: argparse.Namespace) -> int:
    import pandas as pd
    from app.database import SessionLocal
    from app.models.dominion_der import DominionDaIngestionRun

    db = None

    def _session():
        nonlocal db
        if db is None:
            db = SessionLocal()
        return db

    try:
        if args.hourly_from_run is not None:
            hourly_df = fetch_hourly_dataframe_for_run(_session(), args.hourly_from_run)
        else:
            hourly_path = Path(args.hourly_parquet)
            if not hourly_path.exists():
                logger.error("Missing hourly parquet: %s", hourly_path)
                return 1
            hourly_df = pd.read_parquet(hourly_path)

        if args.devices_from_db:
            as_of: Optional[date]
            if args.as_of:
                as_of = datetime.strptime(args.as_of, "%Y-%m-%d").date()
            elif args.hourly_from_run is not None:
                run = _session().get(DominionDaIngestionRun, args.hourly_from_run)
                as_of = run.operating_date if run else None
            else:
                as_of = None
            if as_of is None:
                logger.error(
                    "Use --as-of YYYY-MM-DD with --devices-from-db when not using --hourly-from-run"
                )
                return 1
            devices = fetch_active_devices_for_schedule(_session(), as_of)
        else:
            devices = json.loads(Path(args.devices_json).read_text())
            if not isinstance(devices, list):
                logger.error("devices_json must be a JSON array of objects")
                return 1

        if not devices:
            logger.error("No devices to build a schedule (empty list or no active DB devices)")
            return 1

        peak_hours_ept: Optional[Set[int]] = None
        if args.peak_hours_ept:
            peak_hours_ept = _parse_peak_hours_ept(args.peak_hours_ept)

        out_df = build_dispatch_schedule(
            devices,
            hourly_df,
            enable_period_policy=not args.no_period_policy,
            stressed_abs_threshold_usd=args.stressed_threshold_usd,
            extreme_abs_quantile=args.extreme_quantile,
            stressed_signal_fraction=args.stressed_signal_fraction,
            stressed_peak_only=args.stressed_peak_only,
            peak_hours_ept=peak_hours_ept,
        )

        if args.output:
            outp = Path(args.output)
            outp.parent.mkdir(parents=True, exist_ok=True)
            out_df.to_parquet(outp, index=False)
            logger.info("Wrote %s dispatch rows to %s", len(out_df), outp)

        if args.persist:
            run_id = args.ingestion_run_id
            if run_id is None and args.hourly_from_run is not None:
                run_id = args.hourly_from_run
            if run_id is None:
                logger.error(
                    "Persist requires --ingestion-run-id when hourly data comes from parquet"
                )
                return 1
            n = persist_dispatch_schedule(
                _session(),
                run_id,
                out_df,
                replace_existing=not args.no_replace_schedule,
            )
            _session().commit()
            logger.info("Persisted %s schedule rows for ingestion_run_id=%s", n, run_id)

        if not args.output and not args.persist:
            logger.error("Provide --output and/or --persist")
            return 1

        return 0
    except Exception:
        if db is not None:
            db.rollback()
        raise
    finally:
        if db is not None:
            db.close()


def cmd_asset_map(args: argparse.Namespace) -> int:
    from app.database import SessionLocal
    from dominion_dispatch.asset_map import build_dom_program_asset_nodal_map
    from dominion_dispatch.persist_schedule import fetch_active_devices_for_schedule
    from dominion_dispatch.pnode_coords import load_pnode_coords_json

    db = None
    try:
        if args.devices_from_db or not args.no_dom_boundary:
            db = SessionLocal()

        if args.devices_from_db:
            if not args.as_of:
                logger.error("--as-of YYYY-MM-DD is required with --devices-from-db")
                return 1
            as_of = datetime.strptime(args.as_of, "%Y-%m-%d").date()
            devices = fetch_active_devices_for_schedule(db, as_of)
        else:
            devices = json.loads(Path(args.devices_json).read_text())
            if not isinstance(devices, list):
                logger.error("devices_json must be a JSON array of objects")
                return 1

        pnode_defs = None
        if args.pull_pnode_definitions:
            from src.data_acquisition import pull_pnode_list

            pnode_defs = pull_pnode_list(zone=PJM_ZONE_DOM, force=args.force_pnode_cache)

        pcoords = {}
        if args.pnode_coords_json:
            pcoords = load_pnode_coords_json(Path(args.pnode_coords_json))

        build_dom_program_asset_nodal_map(
            devices,
            project_root=_ROOT,
            output_html=Path(args.output_html),
            pnode_coords=pcoords or None,
            session=db,
            include_dom_boundary=not args.no_dom_boundary,
            geocode_missing_pnodes=args.geocode_pnodes,
            pnode_definitions_df=pnode_defs,
        )
        return 0
    finally:
        if db is not None:
            db.close()


def cmd_devices(args: argparse.Namespace) -> int:
    import pandas as pd

    nodes_path = Path(args.nodes_parquet)
    if not nodes_path.exists():
        logger.error("Missing nodes parquet: %s", nodes_path)
        return 1
    node_df = pd.read_parquet(nodes_path)

    devices = json.loads(Path(args.devices_json).read_text())
    if not isinstance(devices, list):
        logger.error("devices_json must be a JSON array of objects")
        return 1

    out = build_device_da_congestion(node_df, devices)
    outp = Path(args.output)
    outp.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(outp, index=False)
    logger.info("Wrote %s rows to %s", len(out), outp)
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="Dominion DA congestion utilities")
    sub = p.add_subparsers(dest="cmd", required=True)

    f = sub.add_parser("fetch-dom", help="Pull DA node LMPs (incl. congestion) for DOM")
    f.add_argument("--date", required=True, help="Operating day YYYY-MM-DD (EPT)")
    f.add_argument("--end-date", help="Inclusive end day YYYY-MM-DD (optional)")
    f.add_argument("--zone", default=PJM_ZONE_DOM, help="PJM zone id (default DOM)")
    f.add_argument(
        "--lmp-type",
        default=DEFAULT_DA_NODE_LMP_TYPE,
        help="da_hrl_lmps type, e.g. LOAD or GEN",
    )
    f.add_argument("--output", required=True, help="Output .parquet path")
    f.set_defaults(func=cmd_fetch_dom)

    ing = sub.add_parser(
        "ingest-dom",
        help="Fetch DA node LMPs for DOM and persist to Postgres (DATABASE_URL)",
    )
    ing.add_argument("--date", required=True, help="Operating day YYYY-MM-DD (EPT)")
    ing.add_argument("--zone", default=PJM_ZONE_DOM, help="PJM zone id (default DOM)")
    ing.add_argument(
        "--lmp-type",
        default=DEFAULT_DA_NODE_LMP_TYPE,
        help="da_hrl_lmps type (default LOAD)",
    )
    ing.add_argument(
        "--replace-existing",
        action="store_true",
        help="Delete prior successful ingest with same idempotency key and re-pull",
    )
    ing.set_defaults(func=cmd_ingest_dom)

    d = sub.add_parser(
        "devices",
        help="Join existing node parquet with devices JSON → device-hour congestion",
    )
    d.add_argument("--nodes-parquet", required=True)
    d.add_argument(
        "--devices-json",
        required=True,
        help='JSON array, e.g. [{"device_id":"a","pnode_id":123}]',
    )
    d.add_argument("--output", required=True)
    d.set_defaults(func=cmd_devices)

    sch = sub.add_parser(
        "dispatch-schedule",
        help="Build device-hour dispatch table; optional Parquet + Postgres persist",
    )
    hgrp = sch.add_mutually_exclusive_group(required=True)
    hgrp.add_argument(
        "--hourly-parquet",
        help="Node hourly DA data (PJM pull or export with pnode + interval + congestion)",
    )
    hgrp.add_argument(
        "--hourly-from-run",
        type=int,
        metavar="INGESTION_RUN_ID",
        help="Load hourly rows from dominion_da_node_hourly for this ingestion run",
    )
    dgrp = sch.add_mutually_exclusive_group(required=True)
    dgrp.add_argument(
        "--devices-json",
        help='JSON array, e.g. [{"device_id":"a","pnode_id":"123",...}] (settlement zone is always DOM)',
    )
    dgrp.add_argument(
        "--devices-from-db",
        action="store_true",
        help="Use dominion_devices rows active on --as-of (or on DA run operating date)",
    )
    sch.add_argument(
        "--as-of",
        help="YYYY-MM-DD for --devices-from-db when not inferrable from --hourly-from-run",
    )
    sch.add_argument(
        "--persist",
        action="store_true",
        help="Write schedule to dominion_dispatch_device_hourly",
    )
    sch.add_argument(
        "--ingestion-run-id",
        type=int,
        help="FK for persisted rows (defaults to --hourly-from-run when that is set)",
    )
    sch.add_argument(
        "--no-replace-schedule",
        action="store_true",
        help="Do not delete existing schedule rows for this run before insert",
    )
    sch.add_argument(
        "--no-period-policy",
        action="store_true",
        help="Disable stressed/extreme gating; dispatch_signal_program = dispatch_signal",
    )
    sch.add_argument(
        "--stressed-threshold-usd",
        type=float,
        default=DISPATCH_STRESSED_ABS_USD_DEFAULT,
        metavar="USD",
        help="|resolved| ≥ this → stressed tier (default %(default)s $/MWh)",
    )
    sch.add_argument(
        "--extreme-quantile",
        type=float,
        default=DISPATCH_EXTREME_ABS_QUANTILE_DEFAULT,
        metavar="Q",
        help="Per device-day quantile of |resolved| for extreme tier (default %(default)s)",
    )
    sch.add_argument(
        "--stressed-signal-fraction",
        type=float,
        default=DISPATCH_STRESSED_SIGNAL_FRACTION_DEFAULT,
        metavar="F",
        help="Stressed tier: multiply dispatch_signal by this (default %(default)s)",
    )
    sch.add_argument(
        "--stressed-peak-only",
        action="store_true",
        help="Stressed tier only in peak EPT hours (extreme still any hour); default peak 7–22",
    )
    sch.add_argument(
        "--peak-hours-ept",
        metavar="H,H,...",
        help="Override peak hours for --stressed-peak-only (comma-separated 0–23 EPT)",
    )
    sch.add_argument("--output", help="Optional output .parquet path")
    sch.set_defaults(func=cmd_dispatch_schedule)

    am = sub.add_parser(
        "asset-map",
        help="Folium HTML map: DER asset locations and associated PJM pnodes (DOM program)",
    )
    am_dev = am.add_mutually_exclusive_group(required=True)
    am_dev.add_argument(
        "--devices-json",
        help="JSON array with primary_pnode_id, optional asset_lat/asset_lon/asset_display_name/primary_pnode_name",
    )
    am_dev.add_argument(
        "--devices-from-db",
        action="store_true",
        help="Plot dominion_devices active on --as-of",
    )
    am.add_argument(
        "--as-of",
        help="YYYY-MM-DD (required with --devices-from-db)",
    )
    am.add_argument("--output-html", required=True, help="Output .html path")
    am.add_argument(
        "--pnode-coords-json",
        help="Optional JSON {pnode_id: [lat,lon] or {lat,lon}} for nodal pins",
    )
    am.add_argument(
        "--pull-pnode-definitions",
        action="store_true",
        help="Load PJM pnode definitions for DOM (needs PJM_SUBSCRIPTION_KEY; fills coords/names when available)",
    )
    am.add_argument(
        "--force-pnode-cache",
        action="store_true",
        help="With --pull-pnode-definitions, bypass local pnode parquet cache",
    )
    am.add_argument(
        "--geocode-pnodes",
        action="store_true",
        help="Nominatim geocode for pnodes still missing coordinates (~1s each)",
    )
    am.add_argument(
        "--no-dom-boundary",
        action="store_true",
        help="Skip DOM zone outline layer",
    )
    am.set_defaults(func=cmd_asset_map)

    args = p.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
