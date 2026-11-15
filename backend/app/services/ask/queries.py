"""What Ask Shepherd reads from the record: the leader's context, the team, who is
free or away, and the facts passed to the model. Nothing here writes."""

import re
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    Assignment,
    Church,
    Finding,
    Gathering,
    GatheringType,
    Membership,
    Ministry,
    Person,
    Role,
    RoleSkill,
)
from app.db.repositories.reads import is_ministry_leader
from app.domain.enums import (
    AssignmentStatus,
    Experience,
    FindingType,
    MembershipStatus,
)
from app.domain.schemas import (
    RosterGathering,
)
from app.services.briefing import briefing, church_today, roster
from app.services.huddle_replacement import EXPERIENCE_RANK, unavailable_on

LOOKAHEAD_DAYS = 28
MAX_PEOPLE = 6


class AskNotAllowed(PermissionError):
    pass


class AskNotFound(LookupError):
    pass


@dataclass
class TeamMember:
    person_id: uuid.UUID
    name: str
    nicknames: list[str]
    experience: Experience | None = None
    role_ids: set[uuid.UUID] = field(default_factory=set)

    @property
    def first(self) -> str:
        return self.name.split(" ")[0]


@dataclass
class Context:
    session: Session
    church_id: uuid.UUID
    ministry: Ministry
    leader: Person
    tz: ZoneInfo
    today: date
    team: dict[uuid.UUID, TeamMember]

    @property
    def leader_first(self) -> str:
        return self.leader.name.split(" ")[0]


@dataclass
class Place:
    id: uuid.UUID
    gathering: Gathering
    gathering_id: uuid.UUID
    role_id: uuid.UUID
    holder: str  # who has it now


def place_of(ctx: Context, assignment_id: uuid.UUID) -> Place | None:
    """A place on this ministry's roster that someone could take over (not declined)."""
    row = ctx.session.execute(
        select(Assignment, Gathering, Person.name)
        .join(Gathering, Gathering.id == Assignment.gathering_id)
        .join(Person, Person.id == Assignment.person_id)
        .where(
            Assignment.church_id == ctx.church_id,
            Assignment.id == assignment_id,
            Assignment.ministry_id == ctx.ministry.id,
            Assignment.status != AssignmentStatus.DECLINED,
        )
    ).first()
    if row is None:
        return None
    a, g, holder = row
    return Place(a.id, g, g.id, a.role_id, holder)


def why_cant_send(ctx: Context, person_id: uuid.UUID, first: str) -> str | None:
    """Why Shepherd can't send to this person, so the leader copies the message instead."""
    person = ctx.session.get_one(Person, person_id)
    if person.stopped:
        return f"{first} turned messages off. Copy it and send it yourself."
    if not person.opted_in:
        return f"{first} hasn't connected to chat yet. Copy it and send it yourself."
    return None


# ---------------------------------------------------------------------------
# Facts
# ---------------------------------------------------------------------------


def load_context(
    session: Session,
    church_id: uuid.UUID,
    ministry_id: uuid.UUID,
    person_id: uuid.UUID,
    today: date | None,
) -> Context:
    ministry = session.scalar(
        select(Ministry).where(Ministry.church_id == church_id, Ministry.id == ministry_id)
    )
    if ministry is None:
        raise AskNotFound("ministry not found")
    if not is_ministry_leader(session, church_id, ministry_id, person_id):
        raise AskNotAllowed("only this ministry's leaders can ask about it")
    leader = session.get_one(Person, person_id)
    church = session.get_one(Church, church_id)
    return Context(
        session=session,
        church_id=church_id,
        ministry=ministry,
        leader=leader,
        tz=ZoneInfo(church.timezone),
        today=today or church_today(session, church_id),
        team=load_team(session, church_id, ministry_id),
    )


def load_team(
    session: Session, church_id: uuid.UUID, ministry_id: uuid.UUID
) -> dict[uuid.UUID, TeamMember]:
    team: dict[uuid.UUID, TeamMember] = {}
    for person, role_id, experience in session.execute(
        select(Person, RoleSkill.role_id, RoleSkill.experience)
        .join(Membership, Membership.person_id == Person.id)
        .outerjoin(RoleSkill, RoleSkill.membership_id == Membership.id)
        .where(
            Membership.church_id == church_id,
            Membership.ministry_id == ministry_id,
            Membership.status == MembershipStatus.ACTIVE,
            Person.stopped.is_(False),
        )
    ):
        member = team.setdefault(
            person.id, TeamMember(person.id, person.name, list(person.nicknames))
        )
        if role_id is not None:
            member.role_ids.add(role_id)
        if experience is not None and experience_rank(experience) < experience_rank(
            member.experience
        ):
            member.experience = experience
    return team


def match_people(ctx: Context, written: str) -> list[TeamMember]:
    """Team members a name as written could mean. Several means ask; none means not found."""
    q = written.strip().rstrip(".").casefold()
    if not q:
        return []
    exact = [
        m
        for m in ctx.team.values()
        if q == m.name.casefold() or q in (n.rstrip(".").casefold() for n in m.nicknames)
    ]
    if exact:
        return exact
    return sorted(
        (
            m
            for m in ctx.team.values()
            if q == m.first.casefold()
            or m.name.casefold().startswith(q + " ")
            or (len(q) > 2 and m.name.casefold().startswith(q))
        ),
        key=lambda m: m.name,
    )


def named_in(ctx: Context, text: str) -> list[TeamMember]:
    """Team members whose full or first name appears in the text (no model needed)."""
    full = [m for m in ctx.team.values() if re.search(rf"\b{re.escape(m.name)}\b", text, re.I)]
    if full:
        return full
    return [m for m in ctx.team.values() if re.search(rf"\b{re.escape(m.first)}\b", text, re.I)]


def gatherings_on(ctx: Context, day: date) -> list[RosterGathering]:
    out = roster(ctx.session, ctx.church_id, ctx.ministry.id, day, day + timedelta(days=1))
    return [g for g in out.gatherings if g.roles] if out else []


def next_day(ctx: Context) -> date | None:
    out = roster(
        ctx.session,
        ctx.church_id,
        ctx.ministry.id,
        ctx.today,
        ctx.today + timedelta(days=LOOKAHEAD_DAYS),
    )
    days = [
        g.start_at.astimezone(ctx.tz).date() for g in (out.gatherings if out else []) if g.roles
    ]
    return min(days) if days else None


def busy_people(
    ctx: Context, ids: list[uuid.UUID], start: datetime, end: datetime
) -> set[uuid.UUID]:
    return set(
        ctx.session.scalars(
            select(Assignment.person_id)
            .join(Gathering, Gathering.id == Assignment.gathering_id)
            .where(
                Assignment.church_id == ctx.church_id,
                Assignment.person_id.in_(ids),
                Assignment.status != AssignmentStatus.DECLINED,
                Gathering.start_at < end,
                Gathering.end_at > start,
            )
        )
    )


def blocked_on(ctx: Context, ids: list[uuid.UUID], day: date) -> set[uuid.UUID]:
    """Blocked out that day, or declined a place that day."""
    return unavailable_on(ctx.session, ctx.church_id, ids, day, ctx.tz)


def next_assignment(
    ctx: Context, person_id: uuid.UUID, on: date | None
) -> tuple[Assignment, Gathering, Role, str] | None:
    start = datetime.combine(on or ctx.today, time(0), tzinfo=ctx.tz)
    end = start + timedelta(days=1 if on else LOOKAHEAD_DAYS)
    row = ctx.session.execute(
        select(Assignment, Gathering, Role, GatheringType.name)
        .join(Gathering, Gathering.id == Assignment.gathering_id)
        .join(GatheringType, GatheringType.id == Gathering.gathering_type_id)
        .join(Role, Role.id == Assignment.role_id)
        .where(
            Assignment.church_id == ctx.church_id,
            Assignment.ministry_id == ctx.ministry.id,
            Assignment.person_id == person_id,
            Assignment.status != AssignmentStatus.DECLINED,
            Gathering.start_at >= start,
            Gathering.start_at < end,
        )
        .order_by(Gathering.start_at)
        .limit(1)
    ).first()
    return (row[0], row[1], row[2], row[3]) if row else None


def open_overlap(ctx: Context, assignment_id: uuid.UUID) -> uuid.UUID | None:
    brief = briefing(ctx.session, ctx.church_id, ctx.leader.id, ctx.today)
    for item in brief.items:
        if item.type is not FindingType.OVERLAP or not item.can_huddle:
            continue
        finding = ctx.session.get_one(Finding, item.finding_id)
        if str(assignment_id) in finding.details.get("assignment_ids", []):
            return item.finding_id
    return None


def facts_for_model(ctx: Context, question: str) -> str:
    out = roster(
        ctx.session,
        ctx.church_id,
        ctx.ministry.id,
        ctx.today,
        ctx.today + timedelta(days=LOOKAHEAD_DAYS),
    )
    days = sorted(
        {g.start_at.astimezone(ctx.tz).date() for g in (out.gatherings if out else []) if g.roles}
    )
    upcoming = ", ".join(f"{d:%A} {d.isoformat()}" for d in days[:8]) or "none"
    return (
        f"Today: {ctx.today:%A} {ctx.today.isoformat()}\n"
        f"Ministry: {ctx.ministry.name}\n"
        f"Upcoming {ctx.ministry.name} dates: {upcoming}\n\n"
        f"Question: {question}"
    )


def parse_date(value: str | None) -> date | None:
    try:
        return date.fromisoformat(value) if value else None
    except ValueError:
        return None


def experience_rank(experience: Experience | None) -> int:
    return EXPERIENCE_RANK[experience] if experience else len(EXPERIENCE_RANK)
