"""Volunteer chat: the demo simulator's thread, and inbound messages from volunteers.

The simulator stands in for Telegram (no sign-in: it's a demo of the volunteer's side).
`POST .../chat` is the same inbound handling the Telegram webhook will use.
"""

import uuid
from datetime import date

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.ask import AskLLMDep, TodayDep
from app.api.routes import ReaderDep
from app.channels.factory import channel_name
from app.db.models import (
    Church,
    LeaderNotice,
    Membership,
    Ministry,
    MinistryLeader,
    Person,
    SimulatorMessage,
)
from app.db.repositories.notices import NoticeWriter
from app.domain.enums import MembershipStatus
from app.domain.schemas import (
    ChatIn,
    ChatMessageOut,
    ChatReplyOut,
    ChatThreadOut,
    NoticeOut,
    ProposalOut,
    VolunteerOut,
)
from app.services.briefing import church_today
from app.services.errors import NotAllowed
from app.services.inbound import UnknownPerson, handle_inbound
from app.services.proposal_text import describe
from app.services.reminders import draft_reminders

router = APIRouter(tags=["volunteer chat"])


@router.get("/churches/{church_id}/volunteers")
def volunteers(reader: ReaderDep) -> list[VolunteerOut]:
    """People on at least one team, for the demo's "open a volunteer's chat" picker."""
    rows = reader.session.execute(
        select(Person, Ministry.name)
        .join(Membership, Membership.person_id == Person.id)
        .join(Ministry, Ministry.id == Membership.ministry_id)
        .where(Person.church_id == reader.church_id, Membership.status == MembershipStatus.ACTIVE)
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


@router.get("/churches/{church_id}/people/{person_id}/chat")
def thread(reader: ReaderDep, person_id: uuid.UUID) -> ChatThreadOut:
    """Shepherd's side of this one person's 1:1 chat. Never anyone else's messages."""
    person = _person(reader.session, reader.church_id, person_id)
    church = reader.session.get_one(Church, reader.church_id)
    rows = reader.session.scalars(
        select(SimulatorMessage)
        .where(
            SimulatorMessage.church_id == reader.church_id,
            SimulatorMessage.person_id == person_id,
        )
        .order_by(SimulatorMessage.created_at, SimulatorMessage.id)
    ).all()
    return ChatThreadOut(
        person_id=person.id,
        name=person.name,
        church=church.name,
        channel=channel_name(church),
        messages=[_out(m) for m in rows],
    )


@router.post("/churches/{church_id}/people/{person_id}/chat")
def inbound(
    reader: ReaderDep, person_id: uuid.UUID, body: ChatIn, llm: AskLLMDep, today: TodayDep
) -> ChatReplyOut:
    """A volunteer's message. Read by rules (and the model for free text); her answer is
    recorded through the approval queue; the bot's reply lands in her chat."""
    session = reader.session
    before = set(
        session.scalars(
            select(SimulatorMessage.id).where(
                SimulatorMessage.church_id == reader.church_id,
                SimulatorMessage.person_id == person_id,
            )
        )
    )
    try:
        handle_inbound(session, reader.church_id, person_id, body.text, llm, today)
    except UnknownPerson as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error
    session.commit()
    new = session.scalars(
        select(SimulatorMessage)
        .where(
            SimulatorMessage.church_id == reader.church_id,
            SimulatorMessage.person_id == person_id,
            SimulatorMessage.id.not_in(before) if before else SimulatorMessage.id.is_not(None),
        )
        .order_by(SimulatorMessage.created_at, SimulatorMessage.id)
    ).all()
    return ChatReplyOut(replies=[_out(m) for m in new])


@router.post("/churches/{church_id}/ministries/{ministry_id}/reminders/draft")
def draft(reader: ReaderDep, ministry_id: uuid.UUID, today: TodayDep) -> list[ProposalOut]:
    """Draft the coming week's reminders for approval (the worker also does this nightly)."""
    session = reader.session
    on: date = today or church_today(session, reader.church_id)
    proposals = draft_reminders(session, reader.church_id, ministry_id, on)
    session.commit()
    return describe(session, reader.church_id, [ProposalOut.model_validate(p) for p in proposals])


@router.get("/churches/{church_id}/leaders/{person_id}/notices")
def notices(reader: ReaderDep, person_id: uuid.UUID) -> list[NoticeOut]:
    """What volunteers asked Shepherd to pass on, for the ministries this person leads."""
    led = set(
        reader.session.scalars(
            select(MinistryLeader.ministry_id).where(
                MinistryLeader.church_id == reader.church_id, MinistryLeader.person_id == person_id
            )
        )
    )
    rows = reader.session.execute(
        select(LeaderNotice, Person.name)
        .join(Person, Person.id == LeaderNotice.about_person_id)
        .where(LeaderNotice.church_id == reader.church_id, LeaderNotice.ministry_id.in_(led))
        .order_by(LeaderNotice.created_at)
    ).all()
    return [
        NoticeOut(
            id=n.id,
            ministry_id=n.ministry_id,
            about=name,
            kind=n.kind,
            text=n.text,
            note=n.note,
            at=n.created_at,
        )
        for n, name in rows
    ]


@router.delete("/churches/{church_id}/notices/{notice_id}", status_code=status.HTTP_204_NO_CONTENT)
def dismiss(reader: ReaderDep, notice_id: uuid.UUID, person_id: uuid.UUID) -> None:
    """Dismiss a notice: it's deleted, including any personal note it carried."""
    session = reader.session
    notice = session.scalar(
        select(LeaderNotice).where(
            LeaderNotice.church_id == reader.church_id, LeaderNotice.id == notice_id
        )
    )
    if notice is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "notice not found")
    leads = session.scalar(
        select(MinistryLeader.id).where(
            MinistryLeader.church_id == reader.church_id,
            MinistryLeader.ministry_id == notice.ministry_id,
            MinistryLeader.person_id == person_id,
        )
    )
    if leads is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(NotAllowed("not your ministry")))
    NoticeWriter(session, reader.church_id).dismiss(notice_id)
    session.commit()


def _person(session: Session, church_id: uuid.UUID, person_id: uuid.UUID) -> Person:
    person = session.scalar(
        select(Person).where(Person.church_id == church_id, Person.id == person_id)
    )
    if person is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "person not found")
    return person


def _out(m: SimulatorMessage) -> ChatMessageOut:
    return ChatMessageOut(
        id=m.id, body=m.body, buttons=m.buttons, at=m.created_at, approved=m.message_id is not None
    )
