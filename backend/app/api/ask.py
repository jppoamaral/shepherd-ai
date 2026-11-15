"""Ask Shepherd: a leader's questions about their own ministry, answered from the record."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import AskLLMDep, ReaderDep, TodayDep
from app.domain.schemas import AskAnswer, AskIn, AskSendIn, AskSendOut, AskStart
from app.services.ask import ask, ask_start, send_drafts

router = APIRouter(tags=["ask"])


@router.get("/churches/{church_id}/ministries/{ministry_id}/ask")
def start(
    reader: ReaderDep,
    ministry_id: uuid.UUID,
    person_id: Annotated[uuid.UUID, Query(description="The leader asking")],
    today: TodayDep,
) -> AskStart:
    """A greeting and suggested questions built from this week's real data."""
    result = ask_start(reader.session, reader.church_id, ministry_id, person_id, today)
    reader.session.commit()  # the checks behind the suggestions may refresh findings
    return result


@router.post("/churches/{church_id}/ministries/{ministry_id}/ask")
def answer(
    reader: ReaderDep, ministry_id: uuid.UUID, body: AskIn, llm: AskLLMDep, today: TodayDep
) -> AskAnswer:
    """Answer one question. Read-only: drafts come back to read; nothing is stored or sent."""
    result = ask(reader.session, reader.church_id, ministry_id, body, llm, today)
    reader.session.commit()  # same as the briefing: re-running checks may refresh findings
    return result


@router.post("/churches/{church_id}/ministries/{ministry_id}/ask/send")
def send(reader: ReaderDep, ministry_id: uuid.UUID, body: AskSendIn, today: TodayDep) -> AskSendOut:
    """The leader taps Send on drafts: their approval. Sent 1:1 through ApprovalService."""
    result = send_drafts(reader.session, reader.church_id, ministry_id, body, today)
    reader.session.commit()
    return result
