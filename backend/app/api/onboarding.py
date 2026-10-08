"""Onboarding chat endpoints. Everything after the start is scoped to one church."""

import uuid
from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.agents.onboarding import AgentReply, OnboardingAgent, OnboardingNotFound
from app.api.routes import ReaderDep, SessionDep
from app.db.repositories.onboarding import OnboardingRepository
from app.domain.schemas import (
    AgentReplyOut,
    ChatIn,
    OnboardingOut,
    OnboardingStart,
    OnboardingStarted,
)
from app.llm.client import LLMClient
from app.llm.factory import LLMNotConfigured, get_llm
from app.services.errors import ApprovalError
from app.services.onboarding import start_onboarding
from app.services.profile import render_summary

router = APIRouter(tags=["onboarding"])


def llm_dependency() -> LLMClient:
    try:
        return get_llm()
    except LLMNotConfigured as error:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(error)) from error


LLMDep = Annotated[LLMClient, Depends(llm_dependency)]


@router.post("/onboarding", status_code=status.HTTP_201_CREATED)
def start(body: OnboardingStart, session: SessionDep) -> OnboardingStarted:
    """Create a draft church, its admin, and an onboarding session; returns the first question."""
    try:
        started = start_onboarding(session, body.church_name, body.admin_name)
    except ApprovalError as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
    session.commit()
    return OnboardingStarted(
        onboarding_id=started.session.id,
        church_id=started.church.id,
        admin_person_id=started.admin.id,
        topic=started.session.topic,
        message=started.question,
    )


@router.get("/churches/{church_id}/onboarding/{onboarding_id}")
def get_onboarding(reader: ReaderDep, onboarding_id: uuid.UUID) -> OnboardingOut:
    state = OnboardingRepository(reader.session, reader.church_id).get(onboarding_id)
    if state is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "onboarding session not found")
    return OnboardingOut(
        id=state.id,
        status=state.status,
        topic=state.topic,
        pending_question=state.pending_question,
        proposal_id=state.proposal_id,
        summary=render_summary(state.draft),
    )


@router.post("/churches/{church_id}/onboarding/{onboarding_id}/messages")
def send_message(
    reader: ReaderDep, onboarding_id: uuid.UUID, body: ChatIn, llm: LLMDep
) -> AgentReplyOut:
    agent = OnboardingAgent(reader.session, reader.church_id, llm)
    return _respond(reader.session, lambda: agent.handle_message(onboarding_id, body.text))


@router.post("/churches/{church_id}/onboarding/{onboarding_id}/sample")
def send_sample(
    reader: ReaderDep, onboarding_id: uuid.UUID, body: ChatIn, llm: LLMDep
) -> AgentReplyOut:
    """Paste a past schedule; Shepherd suggests what it implies, for you to confirm."""
    agent = OnboardingAgent(reader.session, reader.church_id, llm)
    return _respond(reader.session, lambda: agent.handle_sample(onboarding_id, body.text))


def _respond(session: Session, turn: Callable[[], AgentReply]) -> AgentReplyOut:
    try:
        reply = turn()
    except OnboardingNotFound as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error
    session.commit()
    return AgentReplyOut(
        message=reply.message, topic=reply.topic, status=reply.status, proposal_id=reply.proposal_id
    )
