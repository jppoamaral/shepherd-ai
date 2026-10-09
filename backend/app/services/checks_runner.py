"""Runs the deterministic checks for one church and keeps `Finding` rows current.

Findings are the checks' output, not the record (assignments, messages), so
writing them doesn't go through approval. Re-running is idempotent: a finding is
identified by a stable key, updated while it still applies, and resolved when
it no longer does.
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
from app.services.checks import below_minimum, load, overlaps

CHECKED_TYPES = (FindingType.OVERLAP, FindingType.LOAD, FindingType.BELOW_MINIMUM)
# Load buckets (weeks, months) can start before or end after the window.
CONTEXT = timedelta(days=31)


def run_checks(session: Session, church_id: uuid.UUID, start: date, end: date) -> list[Finding]:
    """Check `[start, end)` (church-local dates); returns the open findings in that window."""
    church = session.get_one(Church, church_id)
    tz = ZoneInfo(church.timezone)
    facts = _assignment_facts(session, church_id, tz, start - CONTEXT, end + CONTEXT)

    rules = [
        LoadRuleFact(r.period, r.normal_max, r.warning_above)
        for r in session.scalars(select(LoadRule).where(LoadRule.church_id == church_id))
    ]
    preferences: dict[object, PreferenceFact] = {
        p.person_id: PreferenceFact(p.preferred_frequency, p.preferred_frequency_period)
        for p in session.scalars(select(Preference).where(Preference.church_id == church_id))
        if p.preferred_frequency is not None and p.preferred_frequency_period is not None
    }

    issues = [
        *overlaps(facts),
        *load(facts, rules, preferences, church.name),
        *below_minimum(_role_needs(session, church_id, tz, facts, start, end)),
    ]
    issues = [i for i in issues if _in_window(i, start, end)]
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
