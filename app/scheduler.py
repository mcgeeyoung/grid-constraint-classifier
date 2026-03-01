"""Lightweight job scheduler for ongoing data operations.

Uses APScheduler to run periodic jobs:
  - Docket watchlist checks (daily)
  - Hosting capacity refresh (weekly)
  - EIA data update (monthly)
  - Data staleness alerts (daily)
  - Coverage snapshot (weekly)

Designed to run as a Heroku worker dyno or standalone process.
Falls back gracefully if dependencies are unavailable.

Usage:
  python -m app.scheduler          # Run scheduler
  python -m app.scheduler --once   # Run all jobs once and exit
  python -m app.scheduler --list   # List registered jobs
"""

import argparse
import logging
import signal
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s [%(name)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("scheduler")


def _record_event(job_name: str, **kwargs):
    """Record a monitor event in the database."""
    try:
        from app.database import SessionLocal
        from app.models.monitor_event import MonitorEvent

        session = SessionLocal()
        try:
            event = MonitorEvent(job_name=job_name, **kwargs)
            session.add(event)
            session.commit()
            return event.id
        except Exception as e:
            session.rollback()
            logger.warning(f"Failed to record event: {e}")
            return None
        finally:
            session.close()
    except Exception:
        return None


def _complete_event(event_id: int, **kwargs):
    """Mark a monitor event as completed."""
    if not event_id:
        return
    try:
        from app.database import SessionLocal
        from app.models.monitor_event import MonitorEvent

        session = SessionLocal()
        try:
            event = session.query(MonitorEvent).get(event_id)
            if event:
                event.completed_at = datetime.now(timezone.utc)
                event.duration_sec = (
                    event.completed_at - event.started_at
                ).total_seconds()
                for k, v in kwargs.items():
                    setattr(event, k, v)
                session.commit()
        except Exception as e:
            session.rollback()
            logger.warning(f"Failed to complete event: {e}")
        finally:
            session.close()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Job definitions
# ---------------------------------------------------------------------------

def job_check_docket_watchlist():
    """Check active docket watchlist entries for new filings."""
    logger.info("Running: docket_watchlist check")
    event_id = _record_event("docket_watchlist")

    checked = 0
    updated = 0
    new_filings = 0
    errors = []

    try:
        from app.database import SessionLocal
        from app.models import DocketWatch
        from adapters.puc_scrapers.registry import get_scraper

        session = SessionLocal()
        try:
            watches = (
                session.query(DocketWatch)
                .filter(DocketWatch.is_active == True)
                .order_by(DocketWatch.priority, DocketWatch.id)
                .all()
            )

            now = datetime.now(timezone.utc)

            for watch in watches:
                # Skip if checked recently (within 20 hours for daily cadence)
                if watch.last_checked_at:
                    hours_since = (now - watch.last_checked_at).total_seconds() / 3600
                    if hours_since < 20:
                        continue

                checked += 1
                try:
                    scraper = get_scraper(watch.state)
                    if not scraper:
                        continue

                    filings = scraper.list_filings(watch.docket_number)
                    watch.last_checked_at = now

                    if len(filings) > watch.filings_count:
                        new_count = len(filings) - watch.filings_count
                        new_filings += new_count
                        watch.filings_count = len(filings)
                        updated += 1

                        if filings:
                            latest = max(filings, key=lambda f: f.filed_date or datetime.min)
                            if latest.filed_date:
                                watch.last_filing_date = latest.filed_date

                        logger.info(
                            f"  {watch.state}/{watch.docket_number}: "
                            f"{new_count} new filing(s)"
                        )

                except Exception as e:
                    errors.append(f"{watch.state}/{watch.docket_number}: {e}")
                    logger.warning(f"  Error checking {watch.docket_number}: {e}")

                # Rate limit between scraper calls
                time.sleep(2)

            session.commit()

        finally:
            session.close()

    except ImportError as e:
        errors.append(f"Import error: {e}")
    except Exception as e:
        errors.append(str(e))

    status = "success" if not errors else ("partial" if checked > 0 else "failed")
    _complete_event(
        event_id,
        status=status,
        records_checked=checked,
        records_updated=updated,
        new_items_found=new_filings,
        summary=f"Checked {checked} watches, {new_filings} new filings",
        error_message="; ".join(errors[:3]) if errors else None,
    )
    logger.info(f"  Done: {checked} checked, {updated} updated, {new_filings} new filings")


def job_check_staleness():
    """Check data freshness and flag stale sources."""
    logger.info("Running: staleness check")
    event_id = _record_event("staleness_check")

    stale_count = 0
    checked = 0
    alerts = []

    try:
        from app.database import SessionLocal
        from app.models import DataCoverage
        from sqlalchemy import func

        session = SessionLocal()
        now = datetime.now(timezone.utc)

        # Staleness thresholds by data type
        thresholds = {
            "hosting_capacity": timedelta(days=180),   # 6 months
            "load_forecast": timedelta(days=365),      # 1 year
            "grid_constraint": timedelta(days=365),    # 1 year
            "interconnection_queue": timedelta(days=90),  # 3 months
            "eia_registry": timedelta(days=365),       # 1 year
            "puc_filings": timedelta(days=30),         # 1 month
            "ferc714": timedelta(days=365),            # 1 year
        }

        try:
            records = session.query(DataCoverage).filter(DataCoverage.has_data == True).all()

            for rec in records:
                checked += 1
                threshold = thresholds.get(rec.data_type, timedelta(days=365))

                if rec.last_updated_at:
                    age = now - rec.last_updated_at
                    if age > threshold:
                        stale_count += 1
                        alerts.append(
                            f"{rec.entity_name}/{rec.data_type}: "
                            f"{age.days}d old (threshold: {threshold.days}d)"
                        )
                elif rec.last_checked_at:
                    age = now - rec.last_checked_at
                    if age > threshold:
                        stale_count += 1

        finally:
            session.close()

    except Exception as e:
        logger.error(f"Staleness check failed: {e}")

    status = "success"
    _complete_event(
        event_id,
        status=status,
        records_checked=checked,
        alerts_generated=stale_count,
        summary=f"Checked {checked} records, {stale_count} stale",
        details_json={"stale_alerts": alerts[:20]} if alerts else None,
    )

    if stale_count > 0:
        alert_msg = f"{stale_count} data sources are stale:\n" + "\n".join(alerts[:5])
        if len(alerts) > 5:
            alert_msg += f"\n... and {len(alerts) - 5} more"
        send_alert("Stale Data Detected", alert_msg, level="warning")

    logger.info(f"  Done: {checked} checked, {stale_count} stale")


def job_coverage_snapshot():
    """Compute and save a coverage snapshot."""
    logger.info("Running: coverage snapshot")
    event_id = _record_event("coverage_snapshot")

    try:
        from app.database import SessionLocal
        from app.models import (
            Utility, DataCoverage, HostingCapacityRecord,
            GridConstraint, LoadForecast, ResourceNeed,
            InterconnectionQueue,
        )

        session = SessionLocal()
        now = datetime.now(timezone.utc)
        saved = 0

        try:
            utilities = session.query(Utility).all()

            data_types_models = [
                ("hosting_capacity", HostingCapacityRecord),
                ("grid_constraint", GridConstraint),
                ("load_forecast", LoadForecast),
                ("resource_need", ResourceNeed),
                ("interconnection_queue", InterconnectionQueue),
            ]

            for utility in utilities:
                for dtype, model in data_types_models:
                    count = (
                        session.query(model)
                        .filter(model.utility_id == utility.id)
                        .count()
                    )

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

        finally:
            session.close()

        _complete_event(
            event_id,
            status="success",
            records_checked=len(utilities) * len(data_types_models),
            records_updated=saved,
            summary=f"Snapshot for {len(utilities)} utilities, {saved} new records",
        )
        logger.info(f"  Done: {saved} new coverage records")

    except Exception as e:
        logger.error(f"Coverage snapshot failed: {e}")
        _complete_event(event_id, status="failed", error_message=str(e))


def job_health_check():
    """Run a health check against DB and Redis, record the result."""
    logger.info("Running: health check")
    event_id = _record_event("health_check")

    checks = {}

    # DB check
    try:
        from sqlalchemy import text
        from app.database import SessionLocal
        session = SessionLocal()
        session.execute(text("SELECT 1"))
        session.close()
        checks["database"] = "ok"
    except Exception as e:
        checks["database"] = f"error: {e}"

    # Redis check
    try:
        from app.cache import get_redis
        r = get_redis()
        if r:
            r.ping()
            checks["redis"] = "ok"
        else:
            checks["redis"] = "unavailable"
    except Exception as e:
        checks["redis"] = f"error: {e}"

    all_ok = all(v == "ok" for v in checks.values())
    status = "success" if all_ok else "partial"
    _complete_event(
        event_id,
        status=status,
        summary=f"DB: {checks.get('database')}, Redis: {checks.get('redis')}",
        details_json=checks,
    )

    if not all_ok:
        send_alert(
            "Health Check Degraded",
            f"DB: {checks.get('database')}, Redis: {checks.get('redis')}",
            level="warning",
        )

    logger.info(f"  Done: {checks}")


def job_hc_refresh():
    """Refresh hosting capacity data for all available utilities."""
    logger.info("Running: hc_refresh")
    event_id = _record_event("hc_refresh")

    checked = 0
    updated = 0
    errors = []

    try:
        from adapters.hosting_capacity.base import UtilityHCConfig
        from adapters.hosting_capacity.registry import get_hc_adapter, list_hc_utilities
        from app.hc_writer import HostingCapacityWriter

        configs_dir = Path(__file__).resolve().parent.parent / "adapters" / "hosting_capacity" / "configs"
        utilities = list_hc_utilities()

        # Skip unavailable or explicitly disabled utilities
        available = []
        for code in utilities:
            cfg = UtilityHCConfig.from_yaml(configs_dir / f"{code}.yaml")
            if cfg.data_source_type != "unavailable" and not cfg.skip:
                available.append(code)
            elif cfg.skip:
                logger.info(f"  {code}: skipped (disabled in config)")

        import hashlib
        from concurrent.futures import ThreadPoolExecutor, as_completed

        def _fetch_one(code):
            """Fetch HC data for one utility (thread-safe, no DB access)."""
            adapter = get_hc_adapter(code)
            df = adapter.pull_hosting_capacity(force=False)
            source_hash = None
            if not df.empty:
                cache_path = adapter.get_cache_path()
                if cache_path.exists():
                    source_hash = hashlib.sha256(cache_path.read_bytes()).hexdigest()
            return code, df, adapter, source_hash

        # Phase 1: Parallel fetch (I/O-bound, no DB access)
        fetch_results = {}
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = {pool.submit(_fetch_one, code): code for code in available}
            for future in as_completed(futures):
                code = futures[future]
                try:
                    code, df, adapter, source_hash = future.result()
                    fetch_results[code] = (df, adapter, source_hash)
                except Exception as e:
                    errors.append(f"{code}: fetch failed: {e}")
                    logger.warning(f"  {code} fetch failed: {e}")

        # Phase 2: Sequential write (DB contention-free)
        for code in available:
            if code not in fetch_results:
                continue
            df, adapter, source_hash = fetch_results[code]
            checked += 1

            if df.empty:
                logger.info(f"  {code}: empty, skipping")
                continue

            writer = HostingCapacityWriter()
            try:
                utility = writer.ensure_utility(adapter.config)

                # Hash check: skip write if data unchanged
                if source_hash:
                    last_hash = writer.get_last_hash(utility.id)
                    if last_hash == source_hash:
                        logger.info(f"  {code}: unchanged (hash match), skipping write")
                        continue

                run = writer.start_run(utility, adapter.resolve_current_url())
                run.records_fetched = len(df)
                if source_hash:
                    run.source_hash = source_hash
                count = writer.write_records(df, utility, run)
                writer.compute_summary(utility)
                writer.complete_run(run)
                updated += count
                logger.info(f"  {code}: {count} records")
            except Exception as e:
                errors.append(f"{code}: {e}")
                logger.warning(f"  {code} write failed: {e}")
            finally:
                writer.close()

    except ImportError as e:
        errors.append(f"Import error: {e}")
    except Exception as e:
        errors.append(str(e))

    status = "success" if not errors else ("partial" if checked > 0 else "failed")
    _complete_event(
        event_id,
        status=status,
        records_checked=checked,
        records_updated=updated,
        summary=f"Refreshed {checked} utilities, {updated} records updated",
        error_message="; ".join(errors[:5]) if errors else None,
    )

    if status == "failed":
        send_alert("HC Refresh Failed", "; ".join(errors[:3]), level="error")

    logger.info(f"  Done: {checked} utilities, {updated} records, {len(errors)} errors")


def job_eia_update():
    """Download and ingest the latest EIA-861 utility data."""
    logger.info("Running: eia_update")
    event_id = _record_event("eia_update")

    errors = []
    record_count = 0

    try:
        from cli.ingest_eia861 import (
            download_eia861, parse_utility_data, parse_sales_data,
            parse_service_territory, _write_to_db,
        )

        data_dir = Path(__file__).resolve().parent.parent / "data" / "eia"
        data_dir.mkdir(parents=True, exist_ok=True)

        # Download latest
        zip_path = download_eia861(data_dir)
        if not zip_path:
            errors.append("Download failed")
        else:
            # Parse
            df_util = parse_utility_data(zip_path)
            df_sales = parse_sales_data(zip_path)
            df_territory = parse_service_territory(zip_path)

            if df_util is not None:
                # Merge
                df = df_util.copy()
                if df_sales is not None:
                    df = df.merge(df_sales, on="utility_id", how="left")
                if df_territory is not None:
                    df = df.merge(df_territory, on="utility_id", how="left")

                record_count = len(df)
                _write_to_db(df)
                logger.info(f"  EIA-861: {record_count} utilities updated")
            else:
                errors.append("Failed to parse utility data")

    except ImportError as e:
        errors.append(f"Import error: {e}")
    except Exception as e:
        errors.append(str(e))
        logger.error(f"  EIA update failed: {e}")

    status = "success" if not errors else "failed"
    _complete_event(
        event_id,
        status=status,
        records_checked=record_count,
        records_updated=record_count if not errors else 0,
        summary=f"EIA-861: {record_count} utilities" if not errors else f"Failed: {errors[0][:200]}",
        error_message="; ".join(errors[:3]) if errors else None,
    )

    if status == "failed":
        send_alert("EIA Update Failed", "; ".join(errors[:3]), level="error")

    logger.info(f"  Done: {record_count} records, status={status}")


def job_ferc_714():
    """Download and import FERC Form 714 planning area data."""
    logger.info("Running: ferc_714")
    event_id = _record_event("ferc_714")

    errors = []
    record_count = 0

    try:
        from adapters.federal_data.ferc714 import FERC714Parser

        data_dir = Path(__file__).resolve().parent.parent / "data" / "ferc"
        data_dir.mkdir(parents=True, exist_ok=True)

        parser = FERC714Parser(data_dir=data_dir)
        zip_path = parser.download_bulk_data()

        if not zip_path:
            errors.append("FERC 714 download failed")
        else:
            # Parse planning areas
            areas = parser.parse_planning_areas()
            logger.info(f"  Parsed {len(areas)} planning areas")

            # Import to DB
            from app.database import SessionLocal
            from app.models import Utility, LoadForecast

            session = SessionLocal()
            try:
                # Build EIA-to-utility mapping
                utilities = {
                    u.eia_id: u.id
                    for u in session.query(Utility).filter(Utility.eia_id.isnot(None)).all()
                }

                for area in areas:
                    utility_id = utilities.get(area.respondent_id)
                    if not utility_id:
                        continue

                    lf = LoadForecast(
                        utility_id=utility_id,
                        forecast_year=area.year or 0,
                        area_name=area.area_name,
                        area_type="planning_area",
                        peak_demand_mw=area.peak_demand_mw,
                        energy_gwh=area.net_energy_gwh,
                        scenario="ferc714_actual",
                    )
                    session.add(lf)
                    record_count += 1

                session.commit()
                logger.info(f"  Imported {record_count} load forecast records")

            except Exception as e:
                session.rollback()
                errors.append(f"DB import failed: {e}")
            finally:
                session.close()

    except ImportError as e:
        errors.append(f"Import error: {e}")
    except Exception as e:
        errors.append(str(e))
        logger.error(f"  FERC 714 update failed: {e}")

    status = "success" if not errors else "failed"
    _complete_event(
        event_id,
        status=status,
        records_checked=record_count,
        records_updated=record_count if not errors else 0,
        summary=f"FERC 714: {record_count} records" if not errors else f"Failed: {errors[0][:200]}",
        error_message="; ".join(errors[:3]) if errors else None,
    )

    if status == "failed":
        send_alert("FERC 714 Import Failed", "; ".join(errors[:3]), level="error")

    logger.info(f"  Done: {record_count} records, status={status}")


def job_eia_930_update():
    """Incremental EIA-930 hourly data pull and congestion score recompute."""
    logger.info("Running: eia_930_update")
    event_id = _record_event("eia_930_update")

    errors = []
    records_fetched = 0
    scores_updated = 0

    try:
        from adapters.eia_client import EIAClient
        from app.database import SessionLocal
        from app.models import BalancingAuthority, BAHourlyData

        session = SessionLocal()
        try:
            bas = session.query(BalancingAuthority).filter(
                BalancingAuthority.is_rto == False,
            ).all()

            client = EIAClient()
            now = datetime.now(timezone.utc)
            since = now - timedelta(days=7)

            for ba in bas:
                try:
                    rows = client.fetch_hourly_data(
                        ba.ba_code,
                        start=since.strftime("%Y-%m-%d"),
                        end=now.strftime("%Y-%m-%d"),
                    )
                    if rows:
                        for row in rows:
                            existing = (
                                session.query(BAHourlyData)
                                .filter_by(
                                    ba_id=ba.id,
                                    timestamp_utc=row.get("timestamp_utc"),
                                )
                                .first()
                            )
                            if not existing:
                                hourly = BAHourlyData(
                                    ba_id=ba.id,
                                    timestamp_utc=row["timestamp_utc"],
                                    demand_mw=row.get("demand_mw"),
                                    net_generation_mw=row.get("net_generation_mw"),
                                    total_interchange_mw=row.get("total_interchange_mw"),
                                )
                                session.add(hourly)
                                records_fetched += 1

                except Exception as e:
                    errors.append(f"{ba.ba_code}: {e}")
                    logger.warning(f"  {ba.ba_code} failed: {e}")

                time.sleep(0.5)

            session.commit()

        finally:
            session.close()

        # Recompute scores if we fetched new data
        if records_fetched > 0:
            try:
                from core.congestion_calculator import CongestionCalculator

                calc = CongestionCalculator()
                year = now.year
                scores_updated = calc.compute_scores(year=year)
                logger.info(f"  Recomputed {scores_updated} congestion scores")
            except Exception as e:
                errors.append(f"Score recompute failed: {e}")
                logger.warning(f"  Score recompute failed: {e}")

    except ImportError as e:
        errors.append(f"Import error: {e}")
    except Exception as e:
        errors.append(str(e))
        logger.error(f"  EIA-930 update failed: {e}")

    status = "success" if not errors else ("partial" if records_fetched > 0 else "failed")
    _complete_event(
        event_id,
        status=status,
        records_checked=records_fetched,
        records_updated=scores_updated,
        new_items_found=records_fetched,
        summary=f"EIA-930: {records_fetched} rows, {scores_updated} scores recomputed",
        error_message="; ".join(errors[:5]) if errors else None,
    )

    if status == "failed":
        send_alert("EIA-930 Update Failed", "; ".join(errors[:3]), level="error")

    logger.info(f"  Done: {records_fetched} rows, {scores_updated} scores, status={status}")


# ---------------------------------------------------------------------------
# Webhook alerting
# ---------------------------------------------------------------------------

def send_alert(title: str, message: str, level: str = "info"):
    """Send an alert via configured webhook (Slack, Discord, or generic).

    Configure via ALERT_WEBHOOK_URL environment variable.
    Supports Slack-format payloads by default.
    """
    import os
    webhook_url = os.environ.get("ALERT_WEBHOOK_URL")
    if not webhook_url:
        logger.debug(f"Alert (no webhook): [{level}] {title}: {message}")
        return

    import requests

    emoji = {"info": ":information_source:", "warning": ":warning:", "error": ":rotating_light:"}.get(level, "")

    payload = {
        "text": f"{emoji} *{title}*\n{message}",
        "username": "Grid Classifier Bot",
    }

    try:
        resp = requests.post(webhook_url, json=payload, timeout=10)
        resp.raise_for_status()
        logger.info(f"Alert sent: {title}")
    except Exception as e:
        logger.warning(f"Alert send failed: {e}")


# ---------------------------------------------------------------------------
# Scheduler setup
# ---------------------------------------------------------------------------

# Job registry with schedule configuration
JOB_REGISTRY = [
    # --- Daily jobs ---
    {
        "id": "docket_watchlist",
        "func": job_check_docket_watchlist,
        "trigger": "cron",
        "hour": 6,
        "minute": 0,
        "description": "Check PUC docket watchlist for new filings",
    },
    {
        "id": "staleness_check",
        "func": job_check_staleness,
        "trigger": "cron",
        "hour": 7,
        "minute": 0,
        "description": "Check data freshness and flag stale sources",
    },
    {
        "id": "eia_930_update",
        "func": job_eia_930_update,
        "trigger": "cron",
        "hour": 4,
        "minute": 0,
        "description": "Incremental EIA-930 hourly data + congestion score recompute",
    },
    # --- Weekly jobs ---
    {
        "id": "coverage_snapshot",
        "func": job_coverage_snapshot,
        "trigger": "cron",
        "day_of_week": "mon",
        "hour": 5,
        "minute": 0,
        "description": "Compute weekly coverage snapshot",
    },
    {
        "id": "hc_refresh",
        "func": job_hc_refresh,
        "trigger": "cron",
        "day_of_week": "sun",
        "hour": 3,
        "minute": 0,
        "description": "Refresh hosting capacity data from all available utilities",
    },
    # --- Annual jobs (run monthly, idempotent on unchanged data) ---
    {
        "id": "eia_update",
        "func": job_eia_update,
        "trigger": "cron",
        "day": 15,
        "hour": 2,
        "minute": 0,
        "description": "Download and ingest EIA-861 utility registry data",
    },
    {
        "id": "ferc_714",
        "func": job_ferc_714,
        "trigger": "cron",
        "day": 15,
        "hour": 2,
        "minute": 30,
        "description": "Download and import FERC Form 714 planning area data",
    },
    # --- High-frequency ---
    {
        "id": "health_check",
        "func": job_health_check,
        "trigger": "interval",
        "minutes": 30,
        "description": "Check DB and Redis connectivity",
    },
]


def create_scheduler():
    """Create and configure the APScheduler instance."""
    try:
        from apscheduler.schedulers.blocking import BlockingScheduler
        from apscheduler.triggers.cron import CronTrigger
        from apscheduler.triggers.interval import IntervalTrigger
    except ImportError:
        logger.error("APScheduler not installed. Run: pip install apscheduler")
        return None

    scheduler = BlockingScheduler(timezone="US/Eastern")

    for job in JOB_REGISTRY:
        trigger_type = job["trigger"]
        trigger_kwargs = {}

        if trigger_type == "cron":
            for key in ("hour", "minute", "day_of_week", "month", "day"):
                if key in job:
                    trigger_kwargs[key] = job[key]
            trigger = CronTrigger(**trigger_kwargs)
        elif trigger_type == "interval":
            for key in ("seconds", "minutes", "hours", "days", "weeks"):
                if key in job:
                    trigger_kwargs[key] = job[key]
            trigger = IntervalTrigger(**trigger_kwargs)
        else:
            continue

        scheduler.add_job(
            job["func"],
            trigger=trigger,
            id=job["id"],
            name=job["description"],
            misfire_grace_time=3600,
            coalesce=True,
        )
        logger.info(f"Registered job: {job['id']} ({job['description']})")

    return scheduler


def run_all_once():
    """Run all registered jobs once (for testing or one-shot execution)."""
    logger.info("Running all jobs once...")
    for job in JOB_REGISTRY:
        try:
            logger.info(f"\n--- {job['id']} ---")
            job["func"]()
        except Exception as e:
            logger.error(f"Job {job['id']} failed: {e}")
    logger.info("\nAll jobs completed.")


def list_jobs():
    """Print all registered jobs."""
    print(f"\n{'Job ID':<25} {'Schedule':<30} {'Description'}")
    print("-" * 85)
    for job in JOB_REGISTRY:
        trigger = job["trigger"]
        if trigger == "cron":
            sched_parts = []
            if "day_of_week" in job:
                sched_parts.append(f"day={job['day_of_week']}")
            if "hour" in job:
                sched_parts.append(f"{job['hour']:02d}:{job.get('minute', 0):02d}")
            schedule = f"cron ({', '.join(sched_parts)})"
        elif trigger == "interval":
            parts = []
            for unit in ("hours", "minutes", "seconds"):
                if unit in job:
                    parts.append(f"{job[unit]} {unit}")
            schedule = f"every {', '.join(parts)}"
        else:
            schedule = trigger

        print(f"{job['id']:<25} {schedule:<30} {job['description']}")


def main():
    parser = argparse.ArgumentParser(description="Grid Classifier scheduler")
    parser.add_argument("--once", action="store_true", help="Run all jobs once and exit")
    parser.add_argument("--list", action="store_true", help="List registered jobs")
    parser.add_argument("--job", help="Run a specific job by ID")
    args = parser.parse_args()

    if args.list:
        list_jobs()
        return

    if args.job:
        job = next((j for j in JOB_REGISTRY if j["id"] == args.job), None)
        if not job:
            print(f"Unknown job: {args.job}")
            print(f"Available: {', '.join(j['id'] for j in JOB_REGISTRY)}")
            return
        job["func"]()
        return

    if args.once:
        run_all_once()
        return

    # Start the scheduler
    scheduler = create_scheduler()
    if not scheduler:
        sys.exit(1)

    # Graceful shutdown
    def _shutdown(signum, frame):
        logger.info("Shutting down scheduler...")
        scheduler.shutdown(wait=False)
        sys.exit(0)

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    logger.info("Scheduler starting...")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        pass


if __name__ == "__main__":
    main()
