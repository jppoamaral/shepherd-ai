"""Applies an approved `leader_roster` proposal. Called only by ApprovalService.

Records the scheduler's own roster as approved assignments (source=leader) and
saves the nicknames the scheduler confirmed while answering questions. It never
creates people or memberships (rule 6): everyone assigned must already be on
the ministry's team.
"""

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    Assignment,
    Membership,
    MinistryLeader,
    Person,
    Proposal,
    ScheduleIntake,
)
from app.db.repositories.assignments import AssignmentWriter
from app.domain.enums import (
    AssignmentSource,
    AssignmentStatus,
    IntakeStatus,
    MembershipStatus,
)
from app.services.errors import ApprovalError

PROPOSAL_TYPE = "leader_roster"


def may_decide(session: Session, proposal: Proposal, person: Person) -> bool:
    """An approver of the ministry the roster is for."""
    return (
        session.scalar(
            select(MinistryLeader.id).where(
                MinistryLeader.church_id == proposal.church_id,
                MinistryLeader.ministry_id == uuid.UUID(proposal.payload["ministry_id"]),
                MinistryLeader.person_id == person.id,
                MinistryLeader.can_approve,
            )
        )
        is not None
    )


def apply(session: Session, proposal: Proposal, approver: Person) -> dict[str, Any]:
    cid = proposal.church_id
    ministry_id = uuid.UUID(proposal.payload["ministry_id"])
    team = set(
        session.scalars(
            select(Membership.person_id).where(
                Membership.church_id == cid,
                Membership.ministry_id == ministry_id,
                Membership.status == MembershipStatus.ACTIVE,
            )
        )
    )
    wanted = [
        (uuid.UUID(a["gathering_id"]), uuid.UUID(a["role_id"]), uuid.UUID(a["person_id"]))
        for a in proposal.payload["assignments"]
    ]
    if outsiders := {person_id for _, _, person_id in wanted} - team:
        raise ApprovalError(
            f"{len(outsiders)} person(s) in this roster aren't on the team any more"
        )

    existing = {
        (row.gathering_id, row.role_id, row.person_id)
        for row in session.execute(
            select(Assignment.gathering_id, Assignment.role_id, Assignment.person_id).where(
                Assignment.church_id == cid,
                Assignment.ministry_id == ministry_id,
                Assignment.status != AssignmentStatus.DECLINED,
            )
        )
    }
    writer = AssignmentWriter(session, cid)
    created = 0
    for gathering_id, role_id, person_id in wanted:
        if (gathering_id, role_id, person_id) in existing:
            continue
        writer.create(
            gathering_id=gathering_id,
            ministry_id=ministry_id,
            role_id=role_id,
            person_id=person_id,
            status=AssignmentStatus.APPROVED,
            source=AssignmentSource.LEADER,
        )
        created += 1

    learned = 0
    for item in proposal.payload.get("nicknames", []):
        person = session.scalar(
            select(Person).where(Person.church_id == cid, Person.id == uuid.UUID(item["person_id"]))
        )
        nickname = str(item["nickname"]).strip()
        if (
            person
            and nickname
            and nickname.casefold() not in {n.casefold() for n in [person.name, *person.nicknames]}
        ):
            person.nicknames = [*person.nicknames, nickname]
            learned += 1

    _set_intake_status(session, proposal, IntakeStatus.APPROVED)
    return {
        "assignments_created": created,
        "duplicates_skipped": len(wanted) - created,
        "nicknames_learned": learned,
    }


def on_reject(session: Session, proposal: Proposal) -> None:
    _set_intake_status(session, proposal, IntakeStatus.REJECTED)


def _set_intake_status(session: Session, proposal: Proposal, status: IntakeStatus) -> None:
    for intake in session.scalars(
        select(ScheduleIntake).where(
            ScheduleIntake.church_id == proposal.church_id,
            ScheduleIntake.proposal_id == proposal.id,
        )
    ):
        intake.status = status
