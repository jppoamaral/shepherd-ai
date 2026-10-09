"""Applies the huddle's "Resolve" and its undo. Called only by ApprovalService.

Resolve: a leader accepts Shepherd's suggested replacement for their own ministry.
The replacement takes the double-booked volunteer's place on that roster, the huddle
closes without a talk, and the checks re-run. Nobody is messaged: not the other
leader, not the volunteer. Undo puts the volunteer back and reopens the huddle.
"""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Assignment, Finding, Huddle, MinistryLeader, Person, Proposal
from app.db.repositories.assignments import AssignmentWriter
from app.domain.enums import AssignmentSource, AssignmentStatus, FindingStatus, HuddleStatus
from app.services.errors import ApprovalError
from app.services.huddle_replacement import (
    ACCEPT_TYPE,
    UNDO_TYPE,
    free_candidates,
    recheck_around,
)

__all__ = ["ACCEPT_TYPE", "UNDO_TYPE", "apply_accept", "apply_undo", "may_decide"]


def may_decide(session: Session, proposal: Proposal, person: Person) -> bool:
    """One of the huddle's two leaders, and an approver of the ministry whose roster changes."""
    huddle = _huddle(session, proposal)
    if huddle is None or person.id not in huddle.leader_person_ids:
        return False
    side = _side_ministry(huddle, proposal)
    if side is None:
        return True  # nothing to undo; apply says so
    return (
        session.scalar(
            select(MinistryLeader.id).where(
                MinistryLeader.church_id == proposal.church_id,
                MinistryLeader.ministry_id == side,
                MinistryLeader.person_id == person.id,
                MinistryLeader.can_approve,
            )
        )
        is not None
    )


def apply_accept(session: Session, proposal: Proposal, approver: Person) -> dict[str, Any]:
    cid = proposal.church_id
    payload = proposal.payload
    huddle = _huddle(session, proposal)
    if huddle is None:
        raise ApprovalError("huddle not found")
    finding = session.get_one(Finding, huddle.finding_id)
    if huddle.status in (HuddleStatus.RESOLVED, HuddleStatus.CANCELLED) or (
        finding.status is not FindingStatus.OPEN
    ):
        raise ApprovalError("This double booking is already settled.")

    assignment_id = uuid.UUID(payload["assignment_id"])
    side = next(
        (s for s in finding.details["sides"] if s["assignment_id"] == str(assignment_id)), None
    )
    assignment = session.scalar(
        select(Assignment).where(Assignment.church_id == cid, Assignment.id == assignment_id)
    )
    volunteer_id = uuid.UUID(payload["from_person_id"])
    replacement_id = uuid.UUID(payload["to_person_id"])
    names = _names(session, cid, [volunteer_id, replacement_id])
    volunteer_first = names[volunteer_id].split(" ")[0]
    if (
        side is None
        or assignment is None
        or assignment.person_id != volunteer_id
        or assignment.status is AssignmentStatus.DECLINED
        or str(assignment.ministry_id) != payload["ministry_id"]
    ):
        raise ApprovalError(f"{volunteer_first}'s place on {payload['ministry']} has changed.")

    free = free_candidates(
        session,
        cid,
        assignment.ministry_id,
        assignment.role_id,
        volunteer_id,
        datetime.fromisoformat(side["start"]),
        datetime.fromisoformat(side["end"]),
    )
    if replacement_id not in {c.person_id for c in free}:
        raise ApprovalError(
            f"{names[replacement_id]} can't take {volunteer_first}'s place any more."
        )

    resolution = {
        "ministry_id": payload["ministry_id"],
        "ministry": payload["ministry"],
        "assignment_id": str(assignment.id),
        "volunteer_id": str(volunteer_id),
        "volunteer": names[volunteer_id],
        "replacement_id": str(replacement_id),
        "replacement": names[replacement_id],
        "resolved_by_id": str(approver.id),
        "resolved_by": approver.name,
        "previous_status": huddle.status.value,
        "previous_reason": assignment.reason,
        "previous_source": assignment.source.value,
        "at": datetime.now(UTC).isoformat(),
    }
    AssignmentWriter(session, cid).reassign(
        assignment,
        person_id=replacement_id,
        reason=f"In {volunteer_first}'s place (settled from the huddle).",
        source=AssignmentSource.LEADER,
    )
    huddle.status = HuddleStatus.RESOLVED
    huddle.outcome = (
        f"{names[replacement_id]} serves in {payload['ministry']} in {volunteer_first}'s place."
    )
    huddle.details = {**huddle.details, "replacement": resolution}
    recheck_around(session, cid, finding)
    session.flush()
    return {
        "huddle_id": str(huddle.id),
        "finding_id": str(finding.id),
        "assignment_id": str(assignment.id),
        "from_person_id": str(volunteer_id),
        "to_person_id": str(replacement_id),
        "finding_status": finding.status.value,
    }


def apply_undo(session: Session, proposal: Proposal, approver: Person) -> dict[str, Any]:
    cid = proposal.church_id
    huddle = _huddle(session, proposal)
    if huddle is None:
        raise ApprovalError("huddle not found")
    resolution = huddle.details.get("replacement")
    if huddle.status is not HuddleStatus.RESOLVED or resolution is None:
        raise ApprovalError("There's nothing to undo.")
    assignment = session.scalar(
        select(Assignment).where(
            Assignment.church_id == cid, Assignment.id == uuid.UUID(resolution["assignment_id"])
        )
    )
    if assignment is None or str(assignment.person_id) != resolution["replacement_id"]:
        raise ApprovalError("The roster has changed since, so this can't be undone here.")

    AssignmentWriter(session, cid).reassign(
        assignment,
        person_id=uuid.UUID(resolution["volunteer_id"]),
        reason=resolution["previous_reason"],
        source=AssignmentSource(resolution["previous_source"]),
    )
    huddle.status = HuddleStatus(resolution["previous_status"])
    huddle.outcome = None
    huddle.details = {k: v for k, v in huddle.details.items() if k != "replacement"}
    finding = session.get_one(Finding, huddle.finding_id)
    recheck_around(session, cid, finding)
    session.flush()
    return {
        "huddle_id": str(huddle.id),
        "assignment_id": str(assignment.id),
        "from_person_id": resolution["replacement_id"],
        "to_person_id": resolution["volunteer_id"],
        "finding_status": finding.status.value,
    }


def _huddle(session: Session, proposal: Proposal) -> Huddle | None:
    return session.scalar(
        select(Huddle).where(
            Huddle.church_id == proposal.church_id,
            Huddle.id == uuid.UUID(proposal.payload["huddle_id"]),
        )
    )


def _side_ministry(huddle: Huddle, proposal: Proposal) -> uuid.UUID | None:
    """The ministry whose roster changes: named by the accept, recorded for the undo."""
    if proposal.type == ACCEPT_TYPE:
        return uuid.UUID(proposal.payload["ministry_id"])
    resolution = huddle.details.get("replacement")
    return uuid.UUID(resolution["ministry_id"]) if resolution else None


def _names(session: Session, church_id: uuid.UUID, ids: list[uuid.UUID]) -> dict[uuid.UUID, str]:
    return dict(
        session.execute(
            select(Person.id, Person.name).where(Person.church_id == church_id, Person.id.in_(ids))
        ).all()
    )
