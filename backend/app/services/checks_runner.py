"""Runs the deterministic checks for one church and keeps `Finding` rows current.

Findings are the checks' output, not the record (assignments, messages), so
writing them doesn't go through approval. Re-running is idempotent: a finding is
identified by a stable key, updated while it still applies, and resolved when
it no longer does.
"""

import uuid
from collections import defaultdict
from collections.abc import Sequence
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    Assignment,
    Blockout,
    Church,
    Finding,
    Gathering,
    GatheringType,
    LoadRule,
    Ministry,
    MinistryLeader,
    Person,
    Preference,
    Role,
    RoleMinimum,
)
from app.domain.checks import AssignmentFact, Issue, LoadRuleFact, PreferenceFact, RoleNeed
from app.domain.enums import AssignmentStatus, FindingStatus, FindingType, Recipient
from app.domain.profile import default_routing
from app.services.checks import below_minimum, blockouts, load, overlaps
from app.services.errors import NotFound

CHECKED_TYPES = (
    FindingType.OVERLAP,
    FindingType.BLOCKOUT,
    FindingType.LOAD,
    FindingType.BELOW_MINIMUM,
)
# Load buckets (weeks, months) can start before or end after the window.
CONTEXT = timedelta(days=31)


def run_checks(session: Session, church_id: uuid.UUID, start: date, end: date) -> list[Finding]:
    """Check `[start, end)` (church-local dates); returns the open findings in that window."""
    church = session.get_one(Church, church_id)
    tz = ZoneInfo(church.timezone)
    facts = _assignment_facts(session, church_id, tz, start - CONTEXT, end + CONTEXT)
    issues = _issues(session, church, tz, facts, start, end)
    recipients = _recipients(session, church, issues)

    existing = {
        f.details.get("key"): f
        for f in session.scalars(
            select(Finding).where(Finding.church_id == church_id, Finding.type.in_(CHECKED_TYPES))
        )
    }
    current: list[Finding] = []
    for issue in issues:
        finding = existing.get(issue.key)
        if finding is None:
            finding = Finding(church_id=church_id, type=issue.type, status=FindingStatus.OPEN)
            session.add(finding)
        elif finding.status is FindingStatus.RESOLVED:
            finding.status = FindingStatus.OPEN
        finding.gathering_id = issue.gathering_id
        finding.person_ids = list(issue.person_ids)
        finding.recipient_person_ids = recipients[issue.key]
        finding.details = {
            **issue.details,
            "key": issue.key,
            "severity": issue.severity,
            "text": issue.text,
            "on": issue.on,
            "ministry_ids": [str(m) for m in issue.ministry_ids],
        }
        if finding.status is FindingStatus.OPEN:
            current.append(finding)

    keys = {i.key for i in issues}
    for key, finding in existing.items():
        on = date.fromisoformat(finding.details.get("on", "1970-01-01"))
        if key not in keys and finding.status is FindingStatus.OPEN and start <= on < end:
            finding.status = FindingStatus.RESOLVED
    session.flush()
    return current


def preview_checks(
    session: Session,
    church_id: uuid.UUID,
    ministry_id: uuid.UUID,
    lines: Sequence[tuple[uuid.UUID, uuid.UUID, uuid.UUID]],
) -> list[Issue]:
    """What approving these (gathering, role, person) places would newly flag. Writes nothing.

    The checks run twice, on the record as it stands and with the places added;
    an issue counts when it is new or its wording changed (a higher count).
    """
    church = session.get_one(Church, church_id)
    tz = ZoneInfo(church.timezone)
    ministry = session.scalar(
        select(Ministry).where(Ministry.church_id == church_id, Ministry.id == ministry_id)
    )
    if ministry is None:
        raise NotFound("ministry not found")
    gatherings = {
        g.id: (g, name)
        for g, name in session.execute(
            select(Gathering, GatheringType.name)
            .join(GatheringType, GatheringType.id == Gathering.gathering_type_id)
            .where(Gathering.church_id == church_id, Gathering.id.in_({g for g, _, _ in lines}))
        )
    }
    people = {
        row.id: row.name
        for row in session.execute(
            select(Person.id, Person.name).where(
                Person.church_id == church_id, Person.id.in_({p for _, _, p in lines})
            )
        )
    }
    roles = {
        row.id: row.name
        for row in session.execute(
            select(Role.id, Role.name).where(
                Role.church_id == church_id,
                Role.ministry_id == ministry_id,
                Role.id.in_({r for _, r, _ in lines}),
            )
        )
    }
    if any(g not in gatherings or r not in roles or p not in people for g, r, p in lines):
        raise NotFound("a gathering, role or person in this roster wasn't found")
    if not lines:
        return []

    days = [g.start_at.astimezone(tz).date() for g, _ in gatherings.values()]
    start, end = min(days), max(days) + timedelta(days=1)
    before = _assignment_facts(session, church_id, tz, start - CONTEXT, end + CONTEXT)
    recorded = {(a.gathering_id, a.role_id, a.person_id) for a in before}
    added = []
    for gathering_id, role_id, person_id in dict.fromkeys(lines):
        if (gathering_id, role_id, person_id) in recorded:
            continue  # already on the roster; approving skips it too
        gathering, gathering_name = gatherings[gathering_id]
        added.append(
            AssignmentFact(
                id=uuid.uuid4(),
                person_id=person_id,
                person_name=people[person_id],
                ministry_id=ministry_id,
                ministry_name=ministry.name,
                role_id=role_id,
                role_name=roles[role_id],
                gathering_id=gathering_id,
                gathering_name=gathering_name,
                start=gathering.start_at,
                end=gathering.end_at,
                local_start=gathering.start_at.astimezone(tz),
                local_end=gathering.end_at.astimezone(tz),
            )
        )
    known = {i.key: i.text for i in _issues(session, church, tz, before, start, end)}
    return [
        issue
        for issue in _issues(session, church, tz, [*before, *added], start, end)
        if known.get(issue.key) != issue.text
    ]


def _issues(
    session: Session,
    church: Church,
    tz: ZoneInfo,
    facts: list[AssignmentFact],
    start: date,
    end: date,
) -> list[Issue]:
    """Every check's issues about `[start, end)`, from these assignment facts."""
    rules = [
        LoadRuleFact(r.period, r.normal_max, r.warning_above)
        for r in session.scalars(select(LoadRule).where(LoadRule.church_id == church.id))
    ]
    preferences: dict[object, PreferenceFact] = {
        p.person_id: PreferenceFact(p.preferred_frequency, p.preferred_frequency_period)
        for p in session.scalars(select(Preference).where(Preference.church_id == church.id))
        if p.preferred_frequency is not None and p.preferred_frequency_period is not None
    }
    blocked: dict[uuid.UUID, list[tuple[date, date]]] = defaultdict(list)
    for b in session.scalars(select(Blockout).where(Blockout.church_id == church.id)):
        blocked[b.person_id].append((b.start_date, b.end_date))
    issues = [
        *overlaps(facts),
        *blockouts(facts, blocked),
        *load(facts, rules, preferences, church.name),
        *below_minimum(_role_needs(session, church.id, tz, facts, start, end)),
    ]
    return [i for i in issues if _in_window(i, start, end)]


def _in_window(issue: Issue, start: date, end: date) -> bool:
    return start <= date.fromisoformat(issue.on) < end


def _assignment_facts(
    session: Session, church_id: uuid.UUID, tz: ZoneInfo, start: date, end: date
) -> list[AssignmentFact]:
    rows = session.execute(
        select(Assignment, Gathering, GatheringType.name, Person.name, Ministry.name, Role.name)
        .join(Gathering, Gathering.id == Assignment.gathering_id)
        .join(GatheringType, GatheringType.id == Gathering.gathering_type_id)
        .join(Person, Person.id == Assignment.person_id)
        .join(Ministry, Ministry.id == Assignment.ministry_id)
        .join(Role, Role.id == Assignment.role_id)
        .where(
            Assignment.church_id == church_id,
            Assignment.status != AssignmentStatus.DECLINED,
            Gathering.start_at >= datetime.combine(start, time(0), tzinfo=tz),
            Gathering.start_at < datetime.combine(end, time(0), tzinfo=tz),
        )
    ).all()
    return [
        AssignmentFact(
            id=a.id,
            person_id=a.person_id,
            person_name=person,
            ministry_id=a.ministry_id,
            ministry_name=ministry,
            role_id=a.role_id,
            role_name=role,
            gathering_id=g.id,
            gathering_name=gathering,
            start=g.start_at,
            end=g.end_at,
            local_start=g.start_at.astimezone(tz),
            local_end=g.end_at.astimezone(tz),
        )
        for a, g, gathering, person, ministry, role in rows
    ]


def _role_needs(
    session: Session,
    church_id: uuid.UUID,
    tz: ZoneInfo,
    facts: list[AssignmentFact],
    start: date,
    end: date,
) -> list[RoleNeed]:
    """Minimums at gatherings in the window where the ministry has started its roster."""
    started: dict[tuple[uuid.UUID, uuid.UUID], AssignmentFact] = {}
    filled: dict[tuple[uuid.UUID, uuid.UUID], int] = defaultdict(int)
    for a in facts:
        if start <= a.local_start.date() < end:
            started.setdefault((a.ministry_id, a.gathering_id), a)
            filled[(a.gathering_id, a.role_id)] += 1
    if not started:
        return []

    gathering_types = {
        row.id: row.gathering_type_id
        for row in session.execute(
            select(Gathering.id, Gathering.gathering_type_id).where(
                Gathering.id.in_({g for _, g in started})
            )
        )
    }
    minimums = session.execute(
        select(RoleMinimum, Role)
        .join(Role, Role.id == RoleMinimum.role_id)
        .where(RoleMinimum.church_id == church_id, RoleMinimum.minimum > 0)
    ).all()
    needs = []
    for (ministry_id, gathering_id), sample in started.items():
        for minimum, role in minimums:
            if (
                role.ministry_id == ministry_id
                and minimum.gathering_type_id == gathering_types[gathering_id]
            ):
                needs.append(
                    RoleNeed(
                        ministry_id=ministry_id,
                        ministry_name=sample.ministry_name,
                        role_id=role.id,
                        role_name=role.name,
                        gathering_id=gathering_id,
                        gathering_name=sample.gathering_name,
                        local_start=sample.local_start,
                        minimum=minimum.minimum,
                        filled=filled[(gathering_id, role.id)],
                    )
                )
    return needs


def _recipients(
    session: Session, church: Church, issues: list[Issue]
) -> dict[str, list[uuid.UUID]]:
    """Warning routing (set in onboarding) applied to each involved ministry's leaders."""
    routing = {r.finding.value: [x.value for x in r.recipients] for r in default_routing()}
    routing.update(church.warning_routing or {})
    leaders = session.scalars(
        select(MinistryLeader).where(MinistryLeader.church_id == church.id)
    ).all()
    result: dict[str, list[uuid.UUID]] = {}
    for issue in issues:
        wanted = set(routing.get(issue.type.value, [Recipient.APPROVER.value]))
        people = [
            leader.person_id
            for leader in leaders
            if leader.ministry_id in issue.ministry_ids
            and (
                (Recipient.SCHEDULER.value in wanted and leader.can_schedule)
                or (Recipient.APPROVER.value in wanted and leader.can_approve)
            )
        ]
        result[issue.key] = list(dict.fromkeys(people))
    return result
