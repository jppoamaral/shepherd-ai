"""Applies an approved `serve_ask` proposal (records each ask and sends it), and the swap
a leader approves once someone said yes to taking another person's place.

Called only by ApprovalService. People who turned messages off ("stop") or who haven't
connected to chat yet are skipped and counted, never messaged. The swap, like the huddle's
Resolve, messages no one: the person whose place it was isn't told by Shepherd.
"""

import uuid
from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.channels.base import OutgoingMessage
from app.channels.factory import channel_for, channel_name
from app.db.models import Assignment, Church, Gathering, Person, Proposal
from app.db.repositories.assignments import AssignmentWriter
from app.db.repositories.messages import MessageWriter
from app.domain.enums import AssignmentSource, AssignmentStatus
from app.services.checks_runner import run_checks
from app.services.errors import ApprovalError
from app.services.huddle_replacement import free_candidates
from app.services.reminders_apply import may_decide
from app.services.serve_ask import BUTTONS, PROPOSAL_TYPE, SWAP_TYPE

__all__ = ["PROPOSAL_TYPE", "SWAP_TYPE", "apply", "apply_swap", "may_decide"]


def apply(session: Session, proposal: Proposal, approver: Person) -> dict[str, Any]:
    cid = proposal.church_id
    church = session.get_one(Church, cid)
    channel = channel_for(session, church)
    writer = MessageWriter(session, cid)
    sent, failed, stopped, not_connected = 0, 0, 0, 0
    for item in proposal.payload["messages"]:
        person = session.scalar(
            select(Person).where(Person.church_id == cid, Person.id == uuid.UUID(item["person_id"]))
        )
        if person is None:
            continue
        if person.stopped:
            stopped += 1
            continue
        if not person.opted_in:
            not_connected += 1
            continue
        message = writer.create(
            person_id=person.id,
            channel=channel_name(church),
            body=item["body"],
            kind="ask",
            gathering_id=uuid.UUID(item["gathering_id"]),
            role_id=uuid.UUID(item["role_id"]),
            replaces_assignment_id=uuid.UUID(item["replaces_assignment_id"])
            if item.get("replaces_assignment_id")
            else None,
            buttons=list(BUTTONS),
        )
        result = channel.send(
            OutgoingMessage(
                message_id=message.id,
                person_id=person.id,
                person_name=person.name,
                channel_identity=person.channel_identity,
                body=item["body"],
                buttons=tuple(BUTTONS),
            )
        )
        writer.mark(message, ok=result.ok, error=result.error)
        sent, failed = sent + result.ok, failed + (not result.ok)
    return {
        "channel": channel_name(church),
        "sent": sent,
        "failed": failed,
        "stopped": stopped,
        "not_connected": not_connected,
    }


def apply_swap(session: Session, proposal: Proposal, approver: Person) -> dict[str, Any]:
    """They said yes, so they take the place over, confirmed. The checks re-run."""
    cid = proposal.church_id
    payload = proposal.payload
    assignment = session.scalar(
        select(Assignment).where(
            Assignment.church_id == cid, Assignment.id == uuid.UUID(payload["assignment_id"])
        )
    )
    from_id = uuid.UUID(payload["from_person_id"])
    to_id = uuid.UUID(payload["to_person_id"])
    names = dict(
        session.execute(
            select(Person.id, Person.name).where(
                Person.church_id == cid, Person.id.in_([from_id, to_id])
            )
        ).all()
    )
    from_first = names[from_id].split(" ")[0]
    if (
        assignment is None
        or assignment.person_id != from_id
        or assignment.status is AssignmentStatus.DECLINED
        or str(assignment.ministry_id) != payload["ministry_id"]
    ):
        raise ApprovalError(f"{from_first}'s place has changed since.")
    gathering = session.get_one(Gathering, assignment.gathering_id)
    free = free_candidates(
        session,
        cid,
        assignment.ministry_id,
        assignment.role_id,
        from_id,
        gathering.start_at,
        gathering.end_at,
    )
    if to_id not in {c.person_id for c in free}:
        raise ApprovalError(f"{names[to_id]} can't take {from_first}'s place any more.")
    writer = AssignmentWriter(session, cid)
    writer.reassign(
        assignment,
        person_id=to_id,
        reason=f"In {from_first}'s place (said yes when asked).",
        source=AssignmentSource.LEADER,
    )
    writer.set_status(assignment, AssignmentStatus.CONFIRMED)
    day = gathering.start_at.date()
    run_checks(session, cid, day - timedelta(days=7), day + timedelta(days=7))
    return {
        "assignment_id": str(assignment.id),
        "from_person_id": str(from_id),
        "to_person_id": str(to_id),
    }
