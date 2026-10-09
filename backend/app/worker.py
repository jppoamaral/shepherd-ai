"""The agent worker: one process running APScheduler.

A nightly job keeps concrete gatherings generated ahead for every church and
re-runs the deterministic checks for the next four weeks.
"""

import logging
from datetime import date, timedelta

from apscheduler.schedulers.blocking import BlockingScheduler
from sqlalchemy import select

from app.config import get_settings
from app.db.models import Church
from app.db.session import get_sessionmaker
from app.services.checks_runner import run_checks
from app.services.gatherings import ensure_gatherings

log = logging.getLogger("shepherd.worker")


def extend_gatherings() -> None:
    horizon = timedelta(weeks=get_settings().gathering_horizon_weeks)
    with get_sessionmaker()() as session:
        for church in session.scalars(select(Church)):
            # Start a day early so no church's "today" is missed across time zones.
            start = date.today() - timedelta(days=1)
            created = ensure_gatherings(session, church.id, start, start + horizon)
            findings = run_checks(session, church.id, start, start + timedelta(weeks=4))
            log.info(
                "church=%s gatherings_created=%d open_findings=%d",
                church.name,
                created,
                len(findings),
            )
        session.commit()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    scheduler = BlockingScheduler(timezone="UTC")
    scheduler.add_job(extend_gatherings, "cron", hour=2, minute=0, id="extend_gatherings")
    extend_gatherings()
    log.info("worker started")
    scheduler.start()


if __name__ == "__main__":
    main()
