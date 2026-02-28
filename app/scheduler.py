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
        from app.database import SessionLocal
        session = SessionLocal()
        session.execute("SELECT 1")
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
    _complete_event(
        event_id,
        status="success" if all_ok else "partial",
        summary=f"DB: {checks.get('database')}, Redis: {checks.get('redis')}",
        details_json=checks,
    )
    logger.info(f"  Done: {checks}")


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
        "id": "coverage_snapshot",
        "func": job_coverage_snapshot,
        "trigger": "cron",
        "day_of_week": "mon",
        "hour": 5,
        "minute": 0,
        "description": "Compute weekly coverage snapshot",
    },
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
