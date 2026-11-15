"""The volunteer chat as the demo simulator shows it: who can be opened, one person's
thread (Shepherd's side only), and taking in a message she sends.

The simulator stands in for Telegram. Her own messages are never stored; only what
Shepherd sent her is kept, so that is all a thread holds.
"""

import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.channels.factory import channel_name
from app.db.models import Church, Membership, Ministry, Person, SimulatorMessage
from app.domain.enums import MembershipStatus
from app.domain.schemas import ChatMessageOut, ChatReplyOut, ChatThreadOut, VolunteerOut
from app.llm.client import LLMClient
from app.services.errors import NotFound
from app.services.inbound import handle_inbound


def volunteers(session: Session, church_id: uuid.UUID) -> list[VolunteerOut]:
    """People on at least one team."""
    rows = session.execute(
        select(Person, Ministry.name)
        .join(Membership, Membership.person_id == Person.id)
        .join(Ministry, Ministry.id == Membership.ministry_id)
        .where(Person.church_id == church_id, Membership.status == MembershipStatus.ACTIVE)
        .order_by(Person.name, Ministry.name)
    ).all()
    out: dict[uuid.UUID, VolunteerOut] = {}
    for person, ministry in rows:
        v = out.setdefault(
            person.id,
            VolunteerOut(
                person_id=person.id,
                name=person.name,
                ministries=[],
                connected=person.opted_in,
                stopped=person.stopped,
            ),
        )
        v.ministries.append(ministry)
    return list(out.values())


def thread(session: Session, church_id: uuid.UUID, person_id: uuid.UUID) -> ChatThreadOut:
    """Shepherd's side of this one person's 1:1 chat. Never anyone else's messages."""
    person = session.scalar(
        select(Person).where(Person.church_id == church_id, Person.id == person_id)
    )
    if person is None:
        raise NotFound("person not found")
    church = session.get_one(Church, church_id)
    return ChatThreadOut(
        person_id=person.id,
        name=person.name,
        church=church.name,
        channel=channel_name(church),
        messages=[_out(m) for m in _messages(session, church_id, person_id)],
    )


def receive(
    session: Session,
    church_id: uuid.UUID,
    person_id: uuid.UUID,
    text: str,
    llm: LLMClient | None,
    today: date | None,
) -> ChatReplyOut:
    """Take in a volunteer's message and return what Shepherd answered. The caller commits."""
    before = {m.id for m in _messages(session, church_id, person_id)}
    handle_inbound(session, church_id, person_id, text, llm, today)
    session.flush()
    new = [m for m in _messages(session, church_id, person_id) if m.id not in before]
    return ChatReplyOut(replies=[_out(m) for m in new])


def _messages(
    session: Session, church_id: uuid.UUID, person_id: uuid.UUID
) -> list[SimulatorMessage]:
    return list(
        session.scalars(
            select(SimulatorMessage)
            .where(SimulatorMessage.church_id == church_id, SimulatorMessage.person_id == person_id)
            .order_by(SimulatorMessage.created_at, SimulatorMessage.id)
        )
    )


def _out(m: SimulatorMessage) -> ChatMessageOut:
    return ChatMessageOut(
        id=m.id, body=m.body, buttons=m.buttons, at=m.created_at, approved=m.message_id is not None
    )
