"""The agent worker: one process running APScheduler.

A nightly job keeps concrete gatherings generated ahead for every church, re-runs the
deterministic checks for the next four weeks, and drafts the coming week's reminders
for leaders to approve.
"""

import logging
from datetime import date, timedelta

from apscheduler.schedulers.blocking import BlockingScheduler
from sqlalchemy import select

from app.config import get_settings
from app.db.models import Church, Ministry
from app.db.session import get_sessionmaker
from app.services.briefing import church_today
from app.services.checks_runner import run_checks
from app.services.gatherings import ensure_gatherings
from app.services.reminders import draft_reminders

log = logging.getLogger("shepherd.worker")


def extend_gatherings() -> None:
    horizon = timedelta(weeks=get_settings().gathering_horizon_weeks)
    with get_sessionmaker()() as session:
        for church in session.scalars(select(Church)):
            # Start a day early so no church's "today" is missed across time zones.
            start = date.today() - timedelta(days=1)
            created = ensure_gatherings(session, church.id, start, start + horizon)
            findings = run_checks(session, church.id, start, start + timedelta(weeks=4))
            # Reminders for the coming week, drafted for leaders to approve (never sent here).
            drafted = sum(
                len(
                    draft_reminders(
                        session, church.id, ministry_id, church_today(session, church.id)
                    )
                )
                for ministry_id in session.scalars(
                    select(Ministry.id).where(Ministry.church_id == church.id)
                )
            )
            log.info(
                "church=%s gatherings_created=%d open_findings=%d reminders_drafted=%d",
                church.name,
                created,
                len(findings),
                drafted,
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
