"""Applies an approved `leader_roster` proposal. Called only by ApprovalService.

Records the scheduler's own roster as approved assignments (source=leader) and
saves the nicknames the scheduler confirmed while answering questions. It never
creates people or memberships (rule 6): everyone assigned must already be on
the ministry's team.
"""

import uuid
from datetime import timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    Assignment,
    Church,
    Gathering,
    Membership,
    Person,
    Proposal,
    ScheduleIntake,
)
from app.db.repositories.assignments import AssignmentWriter
from app.db.repositories.reads import is_ministry_leader
from app.domain.enums import (
    AssignmentSource,
    AssignmentStatus,
    IntakeStatus,
    MembershipStatus,
)
from app.domain.proposals import LeaderRosterPayload
from app.domain.schemas import ProposalOut
from app.services.checks_runner import run_checks
from app.services.errors import ApprovalError
from app.services.names import Names, ProposalText


def may_decide(session: Session, proposal: Proposal, person: Person) -> bool:
    """An approver of the ministry the roster is for."""
    ministry_id = LeaderRosterPayload.model_validate(proposal.payload).ministry_id
    return is_ministry_leader(session, proposal.church_id, ministry_id, person.id, can_approve=True)


def describe(names: Names, proposal: ProposalOut) -> ProposalText:
    payload = LeaderRosterPayload.model_validate(proposal.payload)
    lines = [
        f"• {names.gathering(a.gathering_id)} · {names.role(a.role_id)} · {names.person(a.person_id)}"
        for a in payload.assignments
    ]
    lines += [
        f"• Remember “{n.nickname}” for {names.person(n.person_id)}" for n in payload.nicknames
    ]
    count = len(payload.assignments)
    return ProposalText(
        title=f"{names.ministry(payload.ministry_id)} roster "
        f"({count} assignment{'s' if count != 1 else ''})",
        summary="\n".join(lines),
    )


def apply(session: Session, proposal: Proposal, approver: Person) -> dict[str, Any]:
    cid = proposal.church_id
    payload = LeaderRosterPayload.model_validate(proposal.payload)
    ministry_id = payload.ministry_id
    team = set(
        session.scalars(
            select(Membership.person_id).where(
                Membership.church_id == cid,
                Membership.ministry_id == ministry_id,
                Membership.status == MembershipStatus.ACTIVE,
            )
        )
    )
    # The same person twice in one role at one gathering is one place, not two.
    wanted = list(
        dict.fromkeys((a.gathering_id, a.role_id, a.person_id) for a in payload.assignments)
    )
    reasons = {(a.gathering_id, a.role_id, a.person_id): a.reason for a in payload.assignments}
    # A roster the leader pasted (intake) vs. one Shepherd suggested and the leader approved.
    source = (
        AssignmentSource.SUGGESTION if payload.source == "suggestion" else AssignmentSource.LEADER
    )
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
            source=source,
            reason=reasons.get((gathering_id, role_id, person_id)),
        )
        created += 1

    learned = 0
    for item in payload.nicknames:
        person = session.scalar(
            select(Person).where(Person.church_id == cid, Person.id == item.person_id)
        )
        nickname = item.nickname.strip()
        if (
            person
            and nickname
            and nickname.casefold() not in {n.casefold() for n in [person.name, *person.nicknames]}
        ):
            person.nicknames = [*person.nicknames, nickname]
            learned += 1

    _set_intake_status(session, proposal, IntakeStatus.APPROVED)
    _recheck(session, cid, {gathering_id for gathering_id, _, _ in wanted})
    return {
        "assignments_created": created,
        "duplicates_skipped": len(wanted) - created,
        "nicknames_learned": learned,
    }


def _recheck(session: Session, church_id: uuid.UUID, gathering_ids: set[uuid.UUID]) -> None:
    """Re-run the checks over the days this roster touches, so new warnings show at once."""
    starts = session.scalars(
        select(Gathering.start_at).where(
            Gathering.church_id == church_id, Gathering.id.in_(gathering_ids)
        )
    ).all()
    if not starts:
        return
    tz = ZoneInfo(session.get_one(Church, church_id).timezone)
    days = [s.astimezone(tz).date() for s in starts]
    session.flush()
    run_checks(session, church_id, min(days), max(days) + timedelta(days=1))


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
