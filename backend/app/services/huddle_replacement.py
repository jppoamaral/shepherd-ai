"""Who could take a double-booked volunteer's place, and re-checking after a change.

Shared by the huddle service (to suggest) and the huddle proposal handler (to make
sure the suggestion still fits when a leader accepts it). Deterministic: a free,
not-blocked-out, active member of that ministry with a skill in the same role.
"""

import uuid
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import (
    Assignment,
    Blockout,
    Church,
    Finding,
    Gathering,
    Membership,
    Person,
    RoleSkill,
)
from app.domain.enums import AssignmentStatus, Experience, MembershipStatus
from app.services.checks_runner import run_checks

# Proposal types for "Resolve" and its undo (applied by `huddle_apply`).
ACCEPT_TYPE = "huddle_accept_replacement"
UNDO_TYPE = "huddle_undo_replacement"

EXPERIENCE_RANK = {Experience.VETERAN: 0, Experience.EXPERIENCED: 1, Experience.NEW: 2}


@dataclass(frozen=True)
class Candidate:
    person_id: uuid.UUID
    name: str
    experience: Experience


def free_candidates(
    session: Session,
    church_id: uuid.UUID,
    ministry_id: uuid.UUID,
    role_id: uuid.UUID,
    volunteer_id: uuid.UUID,
    start: datetime,
    end: datetime,
) -> list[Candidate]:
    """Free team members in the role: most experienced first, then lightest week, then name."""
    candidates = session.execute(
        select(Person.id, Person.name, RoleSkill.experience)
        .join(Membership, Membership.person_id == Person.id)
        .join(RoleSkill, RoleSkill.membership_id == Membership.id)
        .where(
            Membership.church_id == church_id,
            Membership.ministry_id == ministry_id,
            Membership.status == MembershipStatus.ACTIVE,
            RoleSkill.role_id == role_id,
            Person.id != volunteer_id,
            Person.stopped.is_(False),
        )
    ).all()
    if not candidates:
        return []
    ids = [c.id for c in candidates]
    busy = set(
        session.scalars(
            select(Assignment.person_id)
            .join(Gathering, Gathering.id == Assignment.gathering_id)
            .where(
                Assignment.church_id == church_id,
                Assignment.person_id.in_(ids),
                Assignment.status != AssignmentStatus.DECLINED,
                Gathering.start_at < end,
                Gathering.end_at > start,
            )
        )
    )
    tz = ZoneInfo(session.get_one(Church, church_id).timezone)
    blocked = unavailable_on(session, church_id, ids, start.astimezone(tz).date(), tz)
    # Lighter week first: assignments within a few days either side of this one.
    week_load: dict[uuid.UUID, int] = {
        person_id: count
        for person_id, count in session.execute(
            select(Assignment.person_id, func.count())
            .join(Gathering, Gathering.id == Assignment.gathering_id)
            .where(
                Assignment.church_id == church_id,
                Assignment.person_id.in_(ids),
                Assignment.status != AssignmentStatus.DECLINED,
                Gathering.start_at >= start - timedelta(days=3),
                Gathering.start_at < start + timedelta(days=4),
            )
            .group_by(Assignment.person_id)
        )
    }
    free = [c for c in candidates if c.id not in busy and c.id not in blocked]
    free.sort(key=lambda c: (EXPERIENCE_RANK[c.experience], week_load.get(c.id, 0), c.name))
    return [Candidate(c.id, c.name, c.experience) for c in free]


def unavailable_on(
    session: Session, church_id: uuid.UUID, ids: list[uuid.UUID], day: date, tz: ZoneInfo
) -> set[uuid.UUID]:
    """People who can't make that (church-local) day: blocked out, or they declined a place
    that day ("I've told your leader you can't make Oct 11"). No reason is looked at."""
    if not ids:
        return set()
    start = datetime.combine(day, time(0), tzinfo=tz)
    blocked = session.scalars(
        select(Blockout.person_id).where(
            Blockout.church_id == church_id,
            Blockout.person_id.in_(ids),
            Blockout.start_date <= day,
            Blockout.end_date >= day,
        )
    )
    declined = session.scalars(
        select(Assignment.person_id)
        .join(Gathering, Gathering.id == Assignment.gathering_id)
        .where(
            Assignment.church_id == church_id,
            Assignment.person_id.in_(ids),
            Assignment.status == AssignmentStatus.DECLINED,
            Gathering.start_at >= start,
            Gathering.start_at < start + timedelta(days=1),
        )
    )
    return set(blocked) | set(declined)


def recheck_around(session: Session, church_id: uuid.UUID, finding: Finding) -> None:
    """Re-run the checks for the week either side of the conflict."""
    on = datetime.fromisoformat(finding.details["sides"][0]["start"]).date()
    run_checks(session, church_id, on - timedelta(days=7), on + timedelta(days=7))
