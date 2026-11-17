"""Synthetic seed data: two churches (see seeds/churches.py)."""

from collections.abc import Callable
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from seeds.churches import grace_community, riverside_fellowship
from seeds.loader import load_church
from seeds.spec import ChurchSeed


def local_today(timezone: str, now: datetime | None = None) -> date:
    """Today's date where the church is, which near midnight differs from the server's (UTC)."""
    return (now or datetime.now(UTC)).astimezone(ZoneInfo(timezone)).date()


def seed_all(session: Session, today: date | None = None) -> dict[str, bool]:
    """Load both churches; returns {church name: created}. Does not commit.

    Without `today`, each church is seeded for its own local date, so its demo
    week is the one its leaders see as "this week" whatever the server's clock says.
    """
    builders: tuple[Callable[[date], ChurchSeed], ...] = (
        lambda _: grace_community(),
        riverside_fellowship,
    )
    results = {}
    for build in builders:
        day = today or local_today(build(date.today()).timezone)
        church, created = load_church(session, build(day), day)
        results[church.name] = created
    return results
