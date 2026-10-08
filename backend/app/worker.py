"""The agent worker: one process running APScheduler.

Milestone 1 has a single job that keeps concrete gatherings generated ahead for
every church. Agents (steward, weekly check, ...) are scheduled here later.
"""

import logging
from datetime import date, timedelta

from apscheduler.schedulers.blocking import BlockingScheduler
from sqlalchemy import select

from app.config import get_settings
from app.db.models import Church
from app.db.session import get_sessionmaker
from app.services.gatherings import ensure_gatherings

log = logging.getLogger("shepherd.worker")


def extend_gatherings() -> None:
    horizon = timedelta(weeks=get_settings().gathering_horizon_weeks)
    with get_sessionmaker()() as session:
        for church in session.scalars(select(Church)):
            # Start a day early so no church's "today" is missed across time zones.
            start = date.today() - timedelta(days=1)
            created = ensure_gatherings(session, church.id, start, start + horizon)
            log.info("church=%s gatherings_created=%d", church.name, created)
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
