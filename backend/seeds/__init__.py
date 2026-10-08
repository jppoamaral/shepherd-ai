"""Synthetic seed data: two churches (see seeds/churches.py)."""

from datetime import date

from sqlalchemy.orm import Session

from seeds.churches import grace_community, riverside_fellowship
from seeds.loader import load_church


def seed_all(session: Session, today: date) -> dict[str, bool]:
    """Load both churches; returns {church name: created}. Does not commit."""
    results = {}
    for spec in (grace_community(), riverside_fellowship(today)):
        church, created = load_church(session, spec, today)
        results[church.name] = created
    return results
