"""Checks against the seeded demo week at Grace (Sun 11 Oct to Sat 17 Oct 2026)."""

import uuid
from datetime import date

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.models import Assignment, Finding, Ministry, Person
from app.domain.enums import FindingStatus, FindingType
from app.services.checks_runner import run_checks

WEEK = (date(2026, 10, 11), date(2026, 10, 18))


def person_id(session: Session, church_id: uuid.UUID, name: str) -> uuid.UUID:
    pid = session.scalar(
        select(Person.id).where(Person.church_id == church_id, Person.name == name)
    )
    assert pid is not None
    return pid


def of_type(findings: list[Finding], kind: FindingType) -> list[Finding]:
    return [f for f in findings if f.type is kind]


def test_demo_week_has_both_double_bookings(session: Session, grace_id: uuid.UUID) -> None:
    findings = run_checks(session, grace_id, *WEEK)
    texts = sorted(f.details["text"] for f in of_type(findings, FindingType.OVERLAP))
    assert texts == [
        "Anna Parker is booked twice at Sunday 9:30 Service (Sun 11 Oct 9:30 AM): Kids (Helper) and Worship (Keys).",
        "Hannah Wright is booked at overlapping times on Wed 14 Oct: Wednesday Prayer Night 7:00 PM to 8:15 PM "
        "(Worship, Vocals) and Wednesday Youth 7:30 PM to 9:00 PM (Media, Sound).",
    ]


def test_double_booking_reaches_both_ministries_leaders(
    session: Session, grace_id: uuid.UUID
) -> None:
    findings = run_checks(session, grace_id, *WEEK)
    anna = person_id(session, grace_id, "Anna Parker")
    (overlap,) = [f for f in of_type(findings, FindingType.OVERLAP) if anna in f.person_ids]
    sarah, david = (
        person_id(session, grace_id, "Sarah Collins"),
        person_id(session, grace_id, "David Morales"),
    )
    assert set(overlap.recipient_person_ids) == {sarah, david}


def test_overloaded_persona_warns_the_approvers(session: Session, grace_id: uuid.UUID) -> None:
    findings = run_checks(session, grace_id, *WEEK)
    anna = person_id(session, grace_id, "Anna Parker")
    (overload,) = [f for f in of_type(findings, FindingType.LOAD) if anna in f.person_ids]
    assert overload.details["severity"] == "warning"
    assert overload.details["count"] == 4
    assert "above their preferred 2" in overload.details["text"]
    sarah, david = (
        person_id(session, grace_id, "Sarah Collins"),
        person_id(session, grace_id, "David Morales"),
    )
    assert set(overload.recipient_person_ids) == {sarah, david}  # approvers of Kids and Worship


def test_below_minimum_only_where_a_roster_has_started(
    session: Session, grace_id: uuid.UUID
) -> None:
    findings = of_type(run_checks(session, grace_id, *WEEK), FindingType.BELOW_MINIMUM)
    worship = session.scalar(
        select(Ministry.id).where(Ministry.church_id == grace_id, Ministry.name == "Worship")
    )
    assert findings and all(
        str(worship) in f.details["ministry_ids"] or f.details["role"] for f in findings
    )
    assert any(
        f.details["text"].startswith("Worship needs 2 Vocals at Sunday 9:30 Service")
        for f in findings
    )
    # Kids at 9:30 is fully staffed in the demo seed, and untouched gatherings aren't "gaps".
    assert not any(f.details["text"].startswith("Kids needs") for f in findings)


def test_rerunning_is_idempotent_and_fixed_conflicts_resolve(
    session: Session, grace_id: uuid.UUID
) -> None:
    first = run_checks(session, grace_id, *WEEK)
    second = run_checks(session, grace_id, *WEEK)
    assert sorted(f.id for f in first) == sorted(f.id for f in second)

    anna = person_id(session, grace_id, "Anna Parker")
    kids = session.scalar(
        select(Ministry.id).where(Ministry.church_id == grace_id, Ministry.name == "Kids")
    )
    session.execute(
        delete(Assignment).where(Assignment.person_id == anna, Assignment.ministry_id == kids)
    )
    third = run_checks(session, grace_id, *WEEK)

    assert not any(f.type is FindingType.OVERLAP and anna in f.person_ids for f in third)
    resolved = session.scalars(
        select(Finding).where(
            Finding.church_id == grace_id, Finding.status == FindingStatus.RESOLVED
        )
    ).all()
    assert any(f.type is FindingType.OVERLAP and anna in f.person_ids for f in resolved)
    # Still 3 this week: above preference and limit stays a warning? 3 > 2 -> yes.
    (load,) = [f for f in third if f.type is FindingType.LOAD and anna in f.person_ids]
    assert load.details["count"] == 3


def test_checks_are_church_scoped(
    session: Session, grace_id: uuid.UUID, riverside_id: uuid.UUID
) -> None:
    run_checks(session, grace_id, *WEEK)
    assert run_checks(session, riverside_id, *WEEK) == []
