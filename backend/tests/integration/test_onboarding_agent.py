"""The onboarding agent end to end with FakeLLM: from nothing to an approved profile."""

import json

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.onboarding import OnboardingAgent
from app.db.models import Church, OnboardingSession, Proposal
from app.domain.enums import OnboardingStatus, ProfileStatus, ProposalStatus
from app.domain.profile import BasicsReply, GatheringsReply, ReviewReply
from app.llm.fake import FakeLLM
from app.services.approval import ApprovalService
from app.services.onboarding import Started, start_onboarding
from app.services.profile import question_for
from tests.profile_script import DONE, SCRIPT, THREE_WEEKS, T


@pytest.fixture
def started(session: Session) -> Started:
    return start_onboarding(session, "Hope Chapel", "Pat Admin")


@pytest.fixture
def llm() -> FakeLLM:
    return FakeLLM()


@pytest.fixture
def agent(session: Session, started: Started, llm: FakeLLM) -> OnboardingAgent:
    return OnboardingAgent(session, started.church.id, llm)


def say(agent: OnboardingAgent, llm: FakeLLM, started: Started, reply, text: str = "…"):  # type: ignore[no-untyped-def]
    llm.queue(reply)
    return agent.handle_message(started.session.id, text)


def test_first_question_asks_about_the_church(started: Started) -> None:
    assert started.question == question_for(T.BASICS)
    assert started.session.topic is T.BASICS


def test_admin_goes_from_nothing_to_an_approved_profile(
    session: Session, started: Started, agent: OnboardingAgent, llm: FakeLLM
) -> None:
    for topic, reply in SCRIPT:
        answer = say(agent, llm, started, reply)
        assert answer.status is OnboardingStatus.ACTIVE, (topic, answer.message)

    assert answer.topic is T.REVIEW
    assert "Wednesday Prayer: every Wednesday at 7:00 PM" in answer.message
    assert (
        "Christmas Eve: Thursday 24 December 2026 at 5:00 PM, 90 minutes, special" in answer.message
    )

    final = say(agent, llm, started, ReviewReply(change_topic=None, **DONE), "Looks right!")
    assert final.status is OnboardingStatus.PROPOSED and final.proposal_id is not None
    proposal = session.get_one(Proposal, final.proposal_id)
    assert (proposal.type, proposal.created_by_agent, proposal.status) == (
        "church_profile",
        "onboarding",
        ProposalStatus.PENDING,
    )
    # Nothing is applied until a person approves.
    assert session.get_one(Church, started.church.id).profile_status is ProfileStatus.DRAFT

    ApprovalService(session).approve(started.church.id, proposal.id, started.admin.id)
    assert session.get_one(Church, started.church.id).profile_status is ProfileStatus.APPROVED


def test_each_answer_moves_to_the_next_question(
    started: Started, agent: OnboardingAgent, llm: FakeLLM
) -> None:
    _, reply = SCRIPT[0]
    answer = say(agent, llm, started, reply)
    assert answer.topic is T.GATHERINGS
    assert answer.message == question_for(T.GATHERINGS)


def test_a_partial_answer_is_echoed_back_for_confirmation(
    started: Started, agent: OnboardingAgent, llm: FakeLLM
) -> None:
    say(agent, llm, started, SCRIPT[0][1])
    partial = SCRIPT[1][1].model_copy(update={"topic_done": False})
    answer = say(agent, llm, started, partial)
    assert answer.topic is T.GATHERINGS
    assert "Wednesday Prayer: every Wednesday at 7:00 PM" in answer.message
    assert "that's all" in answer.message


def test_a_vague_answer_gets_one_question_and_changes_nothing(
    session: Session, started: Started, agent: OnboardingAgent, llm: FakeLLM
) -> None:
    say(agent, llm, started, SCRIPT[0][1])
    before = session.get_one(OnboardingSession, started.session.id).draft
    vague = GatheringsReply(
        gatherings=[],
        topic_done=False,
        clarifying_question="What time does the Sunday morning service start?",
    )
    answer = say(agent, llm, started, vague, "We meet Sunday mornings.")
    assert answer.message == "What time does the Sunday morning service start?"
    assert answer.topic is T.GATHERINGS
    assert session.get_one(OnboardingSession, started.session.id).draft == before


def test_problems_are_explained_and_the_topic_stays(
    started: Started, agent: OnboardingAgent, llm: FakeLLM
) -> None:
    answer = say(agent, llm, started, BasicsReply(timezone="Mars/Olympus", language="en", **DONE))
    assert answer.topic is T.BASICS
    assert "isn't a time zone I recognise" in answer.message


def test_a_sample_schedule_becomes_suggestions_that_block_the_proposal(
    session: Session, started: Started, agent: OnboardingAgent, llm: FakeLLM
) -> None:
    for _, reply in SCRIPT:
        say(agent, llm, started, reply)

    llm.queue(THREE_WEEKS)
    answer = agent.handle_sample(started.session.id, "Sep 2 Worship: Keys - Anna ...")
    assert "From the sample I found" in answer.message
    assert answer.topic is T.GATHERINGS  # gatherings section reopened for confirmation
    assert "please confirm" in answer.message

    # The agent goes back to confirm the suggestions; review (and a proposal) can't happen yet.
    assert answer.status is OnboardingStatus.ACTIVE and answer.proposal_id is None
    assert (
        session.scalars(select(Proposal).where(Proposal.church_id == started.church.id)).all() == []
    )


def test_raw_admin_text_is_never_stored(
    session: Session, started: Started, agent: OnboardingAgent, llm: FakeLLM
) -> None:
    secret = "my brother is in hospital so I'm doing this late"
    say(agent, llm, started, SCRIPT[0][1], f"We're in Dallas. {secret}.")
    llm.queue(THREE_WEEKS)
    agent.handle_sample(started.session.id, f"Schedule pasted by Pat. {secret}")

    row = session.get_one(OnboardingSession, started.session.id)
    stored = json.dumps([row.draft, row.pending_question], default=str)
    assert "hospital" not in stored and "brother" not in stored
    assert "transcript" not in OnboardingSession.__table__.columns


def test_the_model_only_sees_facts_for_the_current_section(
    started: Started, agent: OnboardingAgent, llm: FakeLLM
) -> None:
    for _, reply in SCRIPT[:3]:
        say(agent, llm, started, reply)
    say(agent, llm, started, SCRIPT[3][1], "Keys and vocals for worship")
    call = llm.calls[-1]
    facts = json.loads(
        call["user"].split("\n\nAdministrator's message:")[0].removeprefix("Facts (JSON):\n")
    )
    assert facts["ministries"] == ["Worship", "Kids"]
    assert facts["gatherings"] == ["Sunday Service", "Wednesday Prayer", "Christmas Eve"]
    assert facts["current_section"] == []
    assert "roles" in call["system"].lower()


def test_after_proposing_the_agent_waits_and_calls_no_model(
    started: Started, agent: OnboardingAgent, llm: FakeLLM
) -> None:
    for _, reply in SCRIPT:
        say(agent, llm, started, reply)
    say(agent, llm, started, ReviewReply(change_topic=None, **DONE))
    calls = len(llm.calls)
    answer = agent.handle_message(started.session.id, "Hello?")
    assert answer.status is OnboardingStatus.PROPOSED
    assert "waiting for approval" in answer.message
    assert len(llm.calls) == calls
