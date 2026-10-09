"""Serving reminders (brief §5 step 5): drafted by Shepherd, sent only after approval.

One `reminders` proposal per ministry and gathering, holding one 1:1 message per person
on that roster (never the leader approving it). Approving sends them through the church's
channel (see `reminders_apply`). Wording follows the volunteer chat mockups.
"""

import uuid
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    Assignment,
    Church,
    Gathering,
    Message,
    Ministry,
    MinistryLeader,
    Person,
    Proposal,
    Role,
)
from app.db.repositories.proposals import ProposalRepository
from app.domain.enums import AssignmentStatus, ProposalStatus

PROPOSAL_TYPE = "reminders"
BUTTONS = ["Yes, I'll be there", "I can't make it"]
DAYS_AHEAD = 7


def reminder_text(first: str, ministry: str, role: str, start: datetime, today: date) -> str:
    day = start.date()
    when = f"this {day:%A}" if 0 <= (day - today).days < 7 else f"{day:%A}"
    return (
        f"Hi {first}! You're scheduled in {ministry} {when}, {day:%b} {day.day}, at "
        f"{start.hour % 12 or 12}:{start.minute:02d}, as {role}. Can you make it?"
    )


def draft_reminders(
    session: Session, church_id: uuid.UUID, ministry_id: uuid.UUID, today: date
) -> list[Proposal]:
    """Draft reminders for the ministry's gatherings in the coming week. Idempotent."""
    church = session.get_one(Church, church_id)
    tz = ZoneInfo(church.timezone)
    ministry = session.get_one(Ministry, ministry_id)
    start = datetime.combine(today, time(0), tzinfo=tz)
    rows = session.execute(
        select(Assignment, Gathering, Person, Role.name)
        .join(Gathering, Gathering.id == Assignment.gathering_id)
        .join(Person, Person.id == Assignment.person_id)
        .join(Role, Role.id == Assignment.role_id)
        .where(
            Assignment.church_id == church_id,
            Assignment.ministry_id == ministry_id,
            Assignment.status == AssignmentStatus.APPROVED,
            Gathering.start_at >= start,
            Gathering.start_at < start + timedelta(days=DAYS_AHEAD),
        )
        .order_by(Gathering.start_at, Person.name)
    ).all()
    leaders = set(
        session.scalars(
            select(MinistryLeader.person_id).where(
                MinistryLeader.church_id == church_id, MinistryLeader.ministry_id == ministry_id
            )
        )
    )
    reminded = set(
        session.scalars(
            select(Message.assignment_id).where(
                Message.church_id == church_id, Message.assignment_id.is_not(None)
            )
        )
    )
    pending = {
        (p.payload["gathering_id"])
        for p in session.scalars(
            select(Proposal).where(
                Proposal.church_id == church_id,
                Proposal.type == PROPOSAL_TYPE,
                Proposal.status == ProposalStatus.PENDING,
            )
        )
        if p.payload.get("ministry_id") == str(ministry_id)
    }
    by_gathering: dict[uuid.UUID, list[dict[str, str]]] = {}
    for a, g, person, role in rows:
        if person.id in leaders or a.id in reminded or str(g.id) in pending:
            continue
        local = g.start_at.astimezone(tz)
        by_gathering.setdefault(g.id, []).append(
            {
                "assignment_id": str(a.id),
                "person_id": str(person.id),
                "body": reminder_text(person.name.split(" ")[0], ministry.name, role, local, today),
            }
        )
    repo = ProposalRepository(session, church_id)
    return [
        repo.create(
            type=PROPOSAL_TYPE,
            payload={
                "ministry_id": str(ministry_id),
                "gathering_id": str(gathering_id),
                "messages": messages,
                "buttons": BUTTONS,
            },
            created_by_agent="weekly_check",
        )
        for gathering_id, messages in by_gathering.items()
    ]
