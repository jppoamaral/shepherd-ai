"""Applies an approved `serve_ask` proposal: records each ask and sends it.

Called only by ApprovalService. People who turned messages off ("stop") or who haven't
connected to chat yet are skipped and counted, never messaged.
"""

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.channels.base import OutgoingMessage
from app.channels.factory import channel_for, channel_name
from app.db.models import Church, Person, Proposal
from app.db.repositories.messages import MessageWriter
from app.services.reminders_apply import may_decide
from app.services.serve_ask import BUTTONS, PROPOSAL_TYPE

__all__ = ["PROPOSAL_TYPE", "apply", "may_decide"]


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
