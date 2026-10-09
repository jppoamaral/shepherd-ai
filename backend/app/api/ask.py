"""Ask Shepherd: a leader's questions about their own ministry, answered from the record."""

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.routes import ReaderDep
from app.domain.schemas import AskAnswer, AskIn, AskStart
from app.llm.client import LLMClient
from app.llm.factory import LLMNotConfigured, get_llm
from app.services.ask import AskNotAllowed, AskNotFound, ask, ask_start

router = APIRouter(tags=["ask"])


def ask_llm_dependency() -> LLMClient | None:
    """Typed questions need the model; tapped suggestions don't. None when not configured."""
    try:
        return get_llm()
    except LLMNotConfigured:
        return None


def today_dependency() -> date | None:
    """The church's date for "this week"; None means today. Tests pin it."""
    return None


AskLLMDep = Annotated[LLMClient | None, Depends(ask_llm_dependency)]
TodayDep = Annotated[date | None, Depends(today_dependency)]


@router.get("/churches/{church_id}/ministries/{ministry_id}/ask")
def start(
    reader: ReaderDep,
    ministry_id: uuid.UUID,
    person_id: Annotated[uuid.UUID, Query(description="The leader asking")],
    today: TodayDep,
) -> AskStart:
    """A greeting and suggested questions built from this week's real data."""
    try:
        result = ask_start(reader.session, reader.church_id, ministry_id, person_id, today)
    except AskNotFound as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error
    except AskNotAllowed as error:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(error)) from error
    reader.session.commit()  # the checks behind the suggestions may refresh findings
    return result


@router.post("/churches/{church_id}/ministries/{ministry_id}/ask")
def answer(
    reader: ReaderDep, ministry_id: uuid.UUID, body: AskIn, llm: AskLLMDep, today: TodayDep
) -> AskAnswer:
    """Answer one question. Read-only: drafts come back to copy; nothing is stored or sent."""
    try:
        result = ask(reader.session, reader.church_id, ministry_id, body, llm, today)
    except AskNotFound as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error
    except AskNotAllowed as error:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(error)) from error
    reader.session.commit()  # same as the briefing: re-running checks may refresh findings
    return result
