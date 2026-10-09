"""Weekly briefing and roster views for leaders (brief §5 step 3).

A leader's briefing holds only what concerns them: findings routed to them by
the church's warning routing, and their own ministries' gatherings. Nothing
about another ministry is shown beyond what a shared conflict needs (rule 5).
Text is deterministic so the facts can't drift.
"""

import uuid
from collections import defaultdict
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
    MinistryLeader,
    Person,
    Role,
    RoleMinimum,
    RoleSkill,
)
from app.domain.enums import AssignmentStatus, FindingType
from app.domain.schemas import (
    BriefingGathering,
    BriefingItem,
    BriefingOut,
    GapFill,
    LeaderMinistry,
    LeaderSummary,
    RosterGathering,
    RosterOut,
    RosterPerson,
    RosterRole,
)
from app.services.checks_runner import run_checks
from app.services.huddle_replacement import free_candidates

BRIEFING_DAYS = 7


class NotALeader(LookupError):
    pass


def church_today(session: Session, church_id: uuid.UUID) -> date:
    return datetime.now(ZoneInfo(session.get_one(Church, church_id).timezone)).date()


def leaders(session: Session, church_id: uuid.UUID) -> list[LeaderSummary]:
    rows = session.execute(
        select(MinistryLeader, Person.name, Ministry.name)
        .join(Person, Person.id == MinistryLeader.person_id)
        .join(Ministry, Ministry.id == MinistryLeader.ministry_id)
        .where(MinistryLeader.church_id == church_id)
        .order_by(Person.name, Ministry.name)
    ).all()
    by_person: dict[uuid.UUID, LeaderSummary] = {}
    for leader, person, ministry in rows:
        summary = by_person.setdefault(
            leader.person_id, LeaderSummary(person_id=leader.person_id, name=person, ministries=[])
        )
        summary.ministries.append(
            LeaderMinistry(
                ministry_id=leader.ministry_id,
                ministry=ministry,
                can_schedule=leader.can_schedule,
                can_approve=leader.can_approve,
            )
        )
    return list(by_person.values())


def briefing(
    session: Session, church_id: uuid.UUID, person_id: uuid.UUID, start: date
) -> BriefingOut:
    mine = {
        m.ministry_id: m
        for m in session.scalars(
            select(MinistryLeader).where(
                MinistryLeader.church_id == church_id, MinistryLeader.person_id == person_id
            )
        )
    }
    if not mine:
        raise NotALeader("this person doesn't lead a ministry")
    person = session.get_one(Person, person_id)
    end = start + timedelta(days=BRIEFING_DAYS)
    findings = run_checks(session, church_id, start, end)

    ministry_names = dict(
        session.execute(
            select(Ministry.id, Ministry.name).where(Ministry.church_id == church_id)
        ).all()
    )
    people = dict(
        session.execute(select(Person.id, Person.name).where(Person.church_id == church_id)).all()
    )
    leaders_by_ministry: dict[uuid.UUID, set[uuid.UUID]] = defaultdict(set)
    for leader in session.scalars(
        select(MinistryLeader).where(MinistryLeader.church_id == church_id)
    ):
        leaders_by_ministry[leader.ministry_id].add(leader.person_id)

    items = []
    for f in sorted(findings, key=_order):
        if person_id not in f.recipient_person_ids:
            continue
        ministry_ids = [uuid.UUID(m) for m in f.details.get("ministry_ids", [])]
        others = {p for m in ministry_ids if m not in mine for p in leaders_by_ministry[m]} - {
            person_id
        }
        items.append(
            BriefingItem(
                finding_id=f.id,
                type=f.type,
                severity=f.details["severity"],
                text=f.details["text"],
                on=date.fromisoformat(f.details["on"]),
                ministries=[ministry_names[m] for m in ministry_ids],
                people=[people[p] for p in f.person_ids],
                can_huddle=f.type is FindingType.OVERLAP and bool(others),
                fill=_fill(session, church_id, f, mine)
                if f.type is FindingType.BELOW_MINIMUM
                else None,
            )
        )

    gatherings = _ministry_gatherings(session, church_id, list(mine), start, end)
    warnings = sum(1 for i in items if i.severity == "warning")
    headline = _headline(person.name.split()[0], warnings, len(items) - warnings)
    return BriefingOut(
        person_id=person_id,
        name=person.name,
        start=start,
        end=end,
        headline=headline,
        items=items,
        gatherings=gatherings,
    )


def _headline(first: str, warnings: int, notes: int) -> str:
    if not warnings and not notes:
        return f"{first}, your week looks clear."
    parts = []
    if warnings:
        parts.append(f"{warnings} warning{'s' if warnings > 1 else ''} to look at")
    if notes:
        parts.append(f"{notes} thing{'s' if notes > 1 else ''} to know about")
    return f"{first}, this week you have " + " and ".join(parts) + "."


KIND_ORDER = {FindingType.OVERLAP: 0, FindingType.LOAD: 1, FindingType.BELOW_MINIMUM: 2}


def _order(f: Finding) -> tuple[int, int, str]:
    severity = 0 if f.details.get("severity") == "warning" else 1
    return severity, KIND_ORDER.get(f.type, 9), f.details.get("on", "")


def _fill(
    session: Session, church_id: uuid.UUID, finding: Finding, mine: dict[uuid.UUID, MinistryLeader]
) -> GapFill | None:
    """One free, not-blocked-out team member for an open slot in the leader's own ministry."""
    ministry_ids = [uuid.UUID(m) for m in finding.details.get("ministry_ids", [])]
    if len(ministry_ids) != 1 or ministry_ids[0] not in mine or finding.gathering_id is None:
        return None
    gathering = session.get_one(Gathering, finding.gathering_id)
    role_id = uuid.UUID(finding.details["role_id"])
    free = free_candidates(
        session,
        church_id,
        ministry_ids[0],
        role_id,
        uuid.UUID(int=0),
        gathering.start_at,
        gathering.end_at,
    )
    if not free:
        return None
    return GapFill(
        ministry_id=ministry_ids[0],
        gathering_id=gathering.id,
        role_id=role_id,
        role=finding.details["role"],
        person_id=free[0].person_id,
        name=free[0].name,
        experience=free[0].experience,
    )


def _ministry_gatherings(
    session: Session, church_id: uuid.UUID, ministry_ids: list[uuid.UUID], start: date, end: date
) -> list[BriefingGathering]:
    tz = ZoneInfo(session.get_one(Church, church_id).timezone)
    needs = session.execute(
        select(Role.ministry_id, RoleMinimum.gathering_type_id, RoleMinimum.minimum)
        .join(Role, Role.id == RoleMinimum.role_id)
        .where(
            RoleMinimum.church_id == church_id,
            Role.ministry_id.in_(ministry_ids),
            RoleMinimum.minimum > 0,
        )
    ).all()
    needed: dict[tuple[uuid.UUID, uuid.UUID], int] = defaultdict(int)
    for ministry_id, type_id, minimum in needs:
        needed[(ministry_id, type_id)] += minimum

    gatherings = session.execute(
        select(Gathering, GatheringType.name)
        .join(GatheringType, GatheringType.id == Gathering.gathering_type_id)
        .where(
            Gathering.church_id == church_id,
            Gathering.start_at >= datetime.combine(start, time(0), tzinfo=tz),
            Gathering.start_at < datetime.combine(end, time(0), tzinfo=tz),
        )
        .order_by(Gathering.start_at)
    ).all()
    filled: dict[tuple[uuid.UUID, uuid.UUID], int] = defaultdict(int)
    for ministry_id, gathering_id in session.execute(
        select(Assignment.ministry_id, Assignment.gathering_id).where(
            Assignment.church_id == church_id,
            Assignment.ministry_id.in_(ministry_ids),
            Assignment.status != AssignmentStatus.DECLINED,
        )
    ):
        filled[(ministry_id, gathering_id)] += 1

    names = dict(
        session.execute(
            select(Ministry.id, Ministry.name).where(Ministry.id.in_(ministry_ids))
        ).all()
    )
    return [
        BriefingGathering(
            gathering_id=g.id,
            ministry_id=ministry_id,
            ministry=names[ministry_id],
            name=name,
            start_at=g.start_at.astimezone(tz),
            needed=needed[(ministry_id, g.gathering_type_id)],
            filled=filled[(ministry_id, g.id)],
        )
        for g, name in gatherings
        for ministry_id in ministry_ids
        if needed[(ministry_id, g.gathering_type_id)] or filled[(ministry_id, g.id)]
    ]


def roster(
    session: Session, church_id: uuid.UUID, ministry_id: uuid.UUID, start: date, end: date
) -> RosterOut | None:
    ministry = session.scalar(
        select(Ministry).where(Ministry.church_id == church_id, Ministry.id == ministry_id)
    )
    if ministry is None:
        return None
    church = session.get_one(Church, church_id)
    tz = ZoneInfo(church.timezone)
    findings = run_checks(session, church_id, start, end)
    flags: dict[uuid.UUID, set[str]] = defaultdict(set)
    for f in findings:
        if f.type is FindingType.OVERLAP:
            for assignment_id in f.details.get("assignment_ids", []):
                flags[uuid.UUID(assignment_id)].add("double_booked")
        elif f.type is FindingType.LOAD:
            flag = "over_load" if f.details.get("severity") == "warning" else "above_usual"
            for side in f.details.get("assignments", []):
                flags[uuid.UUID(side["assignment_id"])].add(flag)

    roles = session.scalars(
        select(Role)
        .where(Role.church_id == church_id, Role.ministry_id == ministry_id)
        .order_by(Role.name)
    ).all()
    minimums = {
        (m.role_id, m.gathering_type_id): m.minimum
        for m in session.scalars(
            select(RoleMinimum).where(RoleMinimum.role_id.in_([r.id for r in roles]))
        )
    }
    experience = {
        (person_id, role_id): level
        for person_id, role_id, level in session.execute(
            select(Membership.person_id, RoleSkill.role_id, RoleSkill.experience)
            .join(Membership, Membership.id == RoleSkill.membership_id)
            .where(Membership.church_id == church_id, Membership.ministry_id == ministry_id)
        )
    }
    assigned: dict[tuple[uuid.UUID, uuid.UUID], list[RosterPerson]] = defaultdict(list)
    for a, name in session.execute(
        select(Assignment, Person.name)
        .join(Person, Person.id == Assignment.person_id)
        .where(Assignment.church_id == church_id, Assignment.ministry_id == ministry_id)
        .order_by(Person.name)
    ):
        assigned[(a.gathering_id, a.role_id)].append(
            RosterPerson(
                assignment_id=a.id,
                person_id=a.person_id,
                name=name,
                status=a.status,
                experience=experience.get((a.person_id, a.role_id)),
                flags=sorted(flags.get(a.id, set())),
            )
        )

    gatherings = session.execute(
        select(Gathering, GatheringType)
        .join(GatheringType, GatheringType.id == Gathering.gathering_type_id)
        .where(
            Gathering.church_id == church_id,
            Gathering.start_at >= datetime.combine(start, time(0), tzinfo=tz),
            Gathering.start_at < datetime.combine(end, time(0), tzinfo=tz),
        )
        .order_by(Gathering.start_at)
    ).all()
    result = []
    for g, gathering_type in gatherings:
        rows = []
        for role in roles:
            minimum = minimums.get((role.id, gathering_type.id), 0)
            people = assigned.get((g.id, role.id), [])
            active = [p for p in people if p.status is not AssignmentStatus.DECLINED]
            if minimum or people:
                rows.append(
                    RosterRole(
                        role_id=role.id,
                        role=role.name,
                        minimum=minimum,
                        people=people,
                        missing=max(0, minimum - len(active)),
                    )
                )
        if rows:
            result.append(
                RosterGathering(
                    gathering_id=g.id,
                    name=gathering_type.name,
                    kind=gathering_type.kind,
                    start_at=g.start_at.astimezone(tz),
                    end_at=g.end_at.astimezone(tz),
                    roles=rows,
                )
            )
    return RosterOut(
        ministry_id=ministry.id, ministry=ministry.name, start=start, end=end, gatherings=result
    )
