"""Applies an approved `reminders` proposal: records each message and sends it.

Called only by ApprovalService. People who turned reminders off ("stop") or who
haven't connected to chat yet are skipped and counted, never messaged.
"""

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.channels.base import OutgoingMessage
from app.channels.factory import channel_for, channel_name
from app.db.models import Assignment, Church, MinistryLeader, Person, Proposal
from app.db.repositories.messages import MessageWriter
from app.domain.enums import AssignmentStatus
from app.services.reminders import PROPOSAL_TYPE

__all__ = ["PROPOSAL_TYPE", "apply", "may_decide"]


def may_decide(session: Session, proposal: Proposal, person: Person) -> bool:
    """A leader of the ministry who approves its rosters."""
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
    church = session.get_one(Church, cid)
    channel = channel_for(session, church)
    writer = MessageWriter(session, cid)
    buttons = tuple(proposal.payload.get("buttons", []))
    sent, failed, stopped, not_connected, changed = 0, 0, 0, 0, 0
    for item in proposal.payload["messages"]:
        person = session.scalar(
            select(Person).where(Person.church_id == cid, Person.id == uuid.UUID(item["person_id"]))
        )
        assignment = session.scalar(
            select(Assignment).where(
                Assignment.church_id == cid, Assignment.id == uuid.UUID(item["assignment_id"])
            )
        )
        if (
            person is None
            or assignment is None
            or assignment.person_id != person.id
            or assignment.status is AssignmentStatus.DECLINED
        ):
            changed += 1  # the roster moved on since the draft; nothing to remind
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
            kind="reminder",
            assignment_id=assignment.id,
            buttons=list(buttons),
        )
        result = channel.send(
            OutgoingMessage(
                message_id=message.id,
                person_id=person.id,
                person_name=person.name,
                channel_identity=person.channel_identity,
                body=item["body"],
                buttons=buttons,
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
        "changed": changed,
    }
