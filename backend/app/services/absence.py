"""The absence check (brief §5): active team members who haven't served for a while.

"Last served" is worked out from the record (the latest past assignment that
wasn't declined, or the date the church gave when the team was set up); this
module never marks anything as served. The finding asks the ministry's
approver one question, "still on the team?". Either answer only quiets the
question: membership is an input and is never changed here (rule 6).
"""

import uuid
from datetime import UTC, date, datetime, time
from typing import Literal
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Assignment, Church, Finding, Gathering, Membership, Ministry, Person
from app.domain.checks import MemberFact
from app.domain.enums import AssignmentStatus, FindingStatus, FindingType, MembershipStatus
from app.services.checks import absent
from app.services.checks_runner import recipients_for
from app.services.errors import NotAllowed, NotFound

Answer = Literal["still_here", "later"]


def run_absence_check(session: Session, church_id: uuid.UUID, today: date) -> list[Finding]:
    """Keep the church's absence findings current as of `today`; returns the open ones."""
    church = session.get_one(Church, church_id)
    existing = {
        f.details.get("key"): f
        for f in session.scalars(
            select(Finding).where(
                Finding.church_id == church_id, Finding.type == FindingType.ABSENT
            )
        )
    }
    issues = (
        absent(_members(session, church, today), today, church.absence_threshold_weeks)
        if church.absence_threshold_weeks
        else []
    )
    recipients = recipients_for(session, church, issues)

    current: list[Finding] = []
    for issue in issues:
        finding = existing.get(issue.key)
        if finding is None:
            finding = Finding(church_id=church_id, type=issue.type, status=FindingStatus.OPEN)
            session.add(finding)
        elif finding.status is FindingStatus.DISMISSED:
            # "Yes, still on the team" settles this absence; ask again only after
            # they have served and gone quiet a second time.
            if finding.details.get("last_served") == issue.details["last_served"]:
                continue
            finding.status = FindingStatus.OPEN
        elif finding.status is FindingStatus.RESOLVED:
            finding.status = FindingStatus.OPEN
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
        current.append(finding)

    keys = {i.key for i in issues}
    for key, finding in existing.items():
        if key not in keys and finding.status is FindingStatus.OPEN:
            finding.status = FindingStatus.RESOLVED
    session.flush()
    return current


def answer_absence(
    session: Session,
    church_id: uuid.UUID,
    finding_id: uuid.UUID,
    person_id: uuid.UUID,
    answer: Answer,
) -> None:
    """The approver's answer to "still on the team?". Neither answer changes membership."""
    finding = session.scalar(
        select(Finding).where(
            Finding.church_id == church_id,
            Finding.id == finding_id,
            Finding.type == FindingType.ABSENT,
        )
    )
    if finding is None:
        raise NotFound("check-in not found")
    if person_id not in finding.recipient_person_ids:
        raise NotAllowed("only the ministry's approver can answer this")
    if answer == "still_here":
        finding.status = FindingStatus.DISMISSED
        return
    membership = session.scalar(
        select(Membership).where(
            Membership.church_id == church_id,
            Membership.id == uuid.UUID(finding.details["membership_id"]),
        )
    )
    if membership is not None:
        membership.asked_at = datetime.now(UTC)
    finding.status = FindingStatus.RESOLVED


def _members(session: Session, church: Church, today: date) -> list[MemberFact]:
    tz = ZoneInfo(church.timezone)
    midnight = datetime.combine(today, time(0), tzinfo=tz)
    counted = (Assignment.church_id == church.id, Assignment.status != AssignmentStatus.DECLINED)
    served = {
        (person_id, ministry_id): latest.astimezone(tz).date()
        for person_id, ministry_id, latest in session.execute(
            select(Assignment.person_id, Assignment.ministry_id, func.max(Gathering.start_at))
            .join(Gathering, Gathering.id == Assignment.gathering_id)
            .where(*counted, Gathering.end_at <= midnight)
            .group_by(Assignment.person_id, Assignment.ministry_id)
        )
    }
    upcoming = {
        (person_id, ministry_id)
        for person_id, ministry_id in session.execute(
            select(Assignment.person_id, Assignment.ministry_id)
            .join(Gathering, Gathering.id == Assignment.gathering_id)
            .where(*counted, Gathering.end_at > midnight)
            .distinct()
        )
    }
    rows = session.execute(
        select(Membership, Person.name, Ministry.name)
        .join(Person, Person.id == Membership.person_id)
        .join(Ministry, Ministry.id == Membership.ministry_id)
        .where(Membership.church_id == church.id, Membership.status == MembershipStatus.ACTIVE)
    ).all()
    facts = []
    for membership, person, ministry in rows:
        key = (membership.person_id, membership.ministry_id)
        dates = [d for d in (served.get(key), membership.last_served) if d is not None]
        facts.append(
            MemberFact(
                membership_id=membership.id,
                person_id=membership.person_id,
                person_name=person,
                ministry_id=membership.ministry_id,
                ministry_name=ministry,
                last_served=max(dates) if dates else None,
                asked_on=membership.asked_at.astimezone(tz).date() if membership.asked_at else None,
                upcoming=key in upcoming,
            )
        )
    return facts
