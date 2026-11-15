"""Applies an approved `reminders` proposal: records each message and sends it.

Called only by ApprovalService. People who turned reminders off ("stop") or who
haven't connected to chat yet are skipped and counted, never messaged.
"""

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.channels.base import OutgoingMessage
from app.channels.factory import channel_for, channel_name
from app.db.models import Assignment, Church, Person, Proposal
from app.db.repositories.messages import MessageWriter
from app.db.repositories.reads import is_ministry_leader
from app.domain.enums import ProposalStatus
from app.domain.proposals import RemindersPayload
from app.domain.schemas import ProposalOut
from app.services.names import Names, ProposalText
from app.services.reminders import already_reminded, still_on_roster


def may_decide(session: Session, proposal: Proposal, person: Person) -> bool:
    """A leader of the ministry who approves its rosters."""
    ministry_id = RemindersPayload.model_validate(proposal.payload).ministry_id
    return is_ministry_leader(session, proposal.church_id, ministry_id, person.id, can_approve=True)


def describe(names: Names, proposal: ProposalOut) -> ProposalText:
    """What will be sent, and who is left out because the roster moved on since the draft."""
    payload = RemindersPayload.model_validate(proposal.payload)
    session, cid = names.session, names.church_id
    pending = proposal.status is ProposalStatus.PENDING
    current, left, already = [], [], []
    for m in payload.messages:
        if not still_on_roster(session, cid, m.assignment_id, m.person_id):
            left.append(m)
        elif pending and already_reminded(session, cid, m.assignment_id):
            already.append(m)
        else:
            current.append(m)
    n = len(current)
    blocks = [f"To {names.person(m.person_id)}: {m.body}" for m in current]
    if left:
        who = ", ".join(names.person(m.person_id) for m in left)
        blocks.append(
            f"Not sending to {who}: no longer on this roster since the reminders were drafted."
        )
    if already:
        who = ", ".join(names.person(m.person_id) for m in already)
        blocks.append(f"Not sending to {who}: already reminded from Ask Shepherd.")
    return ProposalText(
        title=f"{n} reminder{'s' if n != 1 else ''} ready for "
        f"{names.gathering(payload.gathering_id)}",
        summary="\n\n".join(blocks),
        count=n,
    )


def apply(session: Session, proposal: Proposal, approver: Person) -> dict[str, Any]:
    cid = proposal.church_id
    church = session.get_one(Church, cid)
    channel = channel_for(session, church)
    writer = MessageWriter(session, cid)
    payload = RemindersPayload.model_validate(proposal.payload)
    buttons = tuple(payload.buttons)
    sent, failed, stopped, not_connected, changed, already = 0, 0, 0, 0, 0, 0
    for item in payload.messages:
        person = session.scalar(
            select(Person).where(Person.church_id == cid, Person.id == item.person_id)
        )
        assignment = session.scalar(
            select(Assignment).where(
                Assignment.church_id == cid, Assignment.id == item.assignment_id
            )
        )
        if (
            person is None
            or assignment is None
            or not still_on_roster(session, cid, item.assignment_id, item.person_id)
        ):
            changed += 1  # the roster moved on since the draft; nothing to remind
            continue
        if already_reminded(session, cid, assignment.id):
            already += 1  # sent meanwhile from Ask Shepherd; never remind twice
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
            body=item.body,
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
                body=item.body,
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
        "already": already,
    }
