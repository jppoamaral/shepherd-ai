"""Dependencies shared by the routers: the request's session, the church it is scoped to,
the language model, and the clock values tests pin."""

import uuid
from datetime import date
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Church
from app.db.repositories.reads import ChurchReader
from app.db.session import get_session
from app.llm.client import LLMClient
from app.llm.factory import LLMNotConfigured, get_llm


def request_session(request: Request, session: Annotated[Session, Depends(get_session)]) -> Session:
    """The request's session, kept on the request so a failed request can be rolled back
    (see `app.api.errors`)."""
    request.state.session = session
    return session


SessionDep = Annotated[Session, Depends(request_session)]


def church_reader(church_id: uuid.UUID, session: SessionDep) -> ChurchReader:
    if session.scalar(select(Church.id).where(Church.id == church_id)) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "church not found")
    return ChurchReader(session, church_id)


ReaderDep = Annotated[ChurchReader, Depends(church_reader)]


def llm_dependency() -> LLMClient:
    """The model, for endpoints that can't work without it."""
    try:
        return get_llm()
    except LLMNotConfigured as error:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(error)) from error


def ask_llm_dependency() -> LLMClient | None:
    """Typed questions need the model; tapped suggestions don't. None when not configured."""
    try:
        return get_llm()
    except LLMNotConfigured:
        return None


def today_dependency() -> date | None:
    """The church's date for "this week"; None means today. Tests pin it."""
    return None


LLMDep = Annotated[LLMClient, Depends(llm_dependency)]
AskLLMDep = Annotated[LLMClient | None, Depends(ask_llm_dependency)]
TodayDep = Annotated[date | None, Depends(today_dependency)]
