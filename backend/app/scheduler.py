"""The nightly job inside the API process (ADR 0002).

Free Render has no background workers, so with `RUN_SCHEDULER=true` the API runs
the worker's job itself: once right after start-up (which also covers waking
from sleep) and then nightly at 02:00 UTC. docker-compose keeps the separate
worker (`app/worker.py`) and leaves this off.
"""

import logging
from datetime import UTC, datetime

from apscheduler.schedulers.background import BackgroundScheduler

from app.worker import extend_gatherings

log = logging.getLogger("shepherd.scheduler")


def build_scheduler() -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone="UTC")
    scheduler.add_job(extend_gatherings, "cron", hour=2, minute=0, id="extend_gatherings")
    # Off the request path, so start-up and the health check aren't held up by it.
    scheduler.add_job(extend_gatherings, "date", run_date=datetime.now(UTC), id="at_startup")
    return scheduler
