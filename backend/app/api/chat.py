"""Volunteer chat: the demo simulator's thread, and inbound messages from volunteers.

The simulator stands in for Telegram (no sign-in: it's a demo of the volunteer's side).
`POST .../chat` is the same inbound handling the Telegram webhook will use.
"""

import uuid
from datetime import date

from fastapi import APIRouter, status

from app.api.deps import AskLLMDep, ReaderDep, TodayDep
from app.domain.schemas import (
    ChatIn,
    ChatReplyOut,
    ChatThreadOut,
    NoticeOut,
    ProposalOut,
    PutInIn,
    PutInOut,
    VolunteerOut,
)
from app.services import chat
from app.services.briefing import church_today
from app.services.notices import dismiss_notice, leader_notices
from app.services.proposal_text import describe
from app.services.put_in import put_in
from app.services.reminders import draft_reminders

router = APIRouter(tags=["volunteer chat"])


@router.get("/churches/{church_id}/volunteers")
def volunteers(reader: ReaderDep) -> list[VolunteerOut]:
    """People on at least one team, for the demo's "open a volunteer's chat" picker."""
    return chat.volunteers(reader.session, reader.church_id)


@router.get("/churches/{church_id}/people/{person_id}/chat")
def thread(reader: ReaderDep, person_id: uuid.UUID) -> ChatThreadOut:
    """Shepherd's side of this one person's 1:1 chat. Never anyone else's messages."""
    return chat.thread(reader.session, reader.church_id, person_id)


@router.post("/churches/{church_id}/people/{person_id}/chat")
def inbound(
    reader: ReaderDep, person_id: uuid.UUID, body: ChatIn, llm: AskLLMDep, today: TodayDep
) -> ChatReplyOut:
    """A volunteer's message. Read by rules (and the model for free text); her answer is
    recorded through the approval queue; the bot's reply lands in her chat."""
    replies = chat.receive(reader.session, reader.church_id, person_id, body.text, llm, today)
    reader.session.commit()
    return replies


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
    return leader_notices(reader.session, reader.church_id, person_id)


@router.delete("/churches/{church_id}/notices/{notice_id}", status_code=status.HTTP_204_NO_CONTENT)
def dismiss(reader: ReaderDep, notice_id: uuid.UUID, person_id: uuid.UUID) -> None:
    """Dismiss a notice: it's deleted, including any personal note it carried."""
    dismiss_notice(reader.session, reader.church_id, notice_id, person_id)
    reader.session.commit()


@router.post("/churches/{church_id}/notices/{notice_id}/put-in")
def put_in_from_notice(reader: ReaderDep, notice_id: uuid.UUID, body: PutInIn) -> PutInOut:
    """Someone said yes when asked: the leader's tap puts them in (a swap if they were asked
    to take someone's place). Approved and audited through ApprovalService."""
    result = put_in(reader.session, reader.church_id, notice_id, body.person_id)
    reader.session.commit()
    return result
