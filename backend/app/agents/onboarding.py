"""Onboarding agent: interviews a church admin and proposes the church profile.

Per turn it asks the model to parse the admin's message into the current
section, lets `app.services.profile` (deterministic) merge and validate it, and
replies with the next question, a clarifying question, or the summary. When the
admin approves the summary it creates a `church_profile` Proposal; only
ApprovalService can apply it (rule 1). Admin messages and pasted schedules are
never stored, only the structured draft.
"""

import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.db.repositories.onboarding import OnboardingRepository, OnboardingState
from app.db.repositories.proposals import ProposalRepository
from app.domain.enums import OnboardingStatus, OnboardingTopic
from app.domain.profile import REPLY_SCHEMAS, ChurchProfileDraft, SampleReply
from app.llm.client import LLMClient
from app.llm.prompts import onboarding as prompts
from app.services.profile import (
    all_leaders,
    apply_reply,
    infer_from_sample,
    next_topic,
    question_for,
    render_section,
    render_summary,
)

AGENT_NAME = "onboarding"
PROPOSAL_TYPE = "church_profile"
T = OnboardingTopic

# Sections that arrive pre-filled with defaults, so the admin is shown them with the question.
SHOW_DEFAULTS = {T.ROUTING, T.ROSTER_SETTINGS}


class OnboardingNotFound(LookupError):
    pass


@dataclass(frozen=True)
class AgentReply:
    message: str
    topic: OnboardingTopic
    status: OnboardingStatus
    proposal_id: uuid.UUID | None = None


class OnboardingAgent:
    def __init__(self, session: Session, church_id: uuid.UUID, llm: LLMClient) -> None:
        self.church_id = church_id
        self.llm = llm
        self.sessions = OnboardingRepository(session, church_id)
        self.proposals = ProposalRepository(session, church_id)

    def handle_message(self, onboarding_id: uuid.UUID, text: str) -> AgentReply:
        state = self._load(onboarding_id)
        if state.status is not OnboardingStatus.ACTIVE:
            return self._closed(state)

        topic = state.topic
        reply = self.llm.complete(
            system=f"{prompts.SYSTEM}\n{prompts.TOPIC_GUIDANCE[topic]}",
            user=self._user_prompt(state, text),
            schema=REPLY_SCHEMAS[topic],
        )
        result = apply_reply(state.draft, topic, reply)
        state.draft = result.draft

        if result.ready_to_propose:
            proposal = self.proposals.create(
                type=PROPOSAL_TYPE,
                payload=state.draft.model_dump(mode="json"),
                created_by_agent=AGENT_NAME,
            )
            state.status, state.proposal_id = OnboardingStatus.PROPOSED, proposal.id
            message = (
                "Thank you! I've sent the profile for approval. Nothing runs until an "
                "admin approves it."
            )
        elif result.clarifying_question:
            message = result.clarifying_question
        elif result.problems:
            message = (
                "I can't take that as it is yet:\n"
                + "\n".join(f"• {p}" for p in result.problems)
                + f"\n\nHere's what I have now:\n{render_section(state.draft, topic)}"
            )
        else:
            message = self._advance(state, topic)

        state.pending_question = message
        self.sessions.save(state)
        return AgentReply(message, state.topic, state.status, state.proposal_id)

    def handle_sample(self, onboarding_id: uuid.UUID, text: str) -> AgentReply:
        """Read a pasted schedule; add what it implies as suggestions to confirm."""
        state = self._load(onboarding_id)
        if state.status is not OnboardingStatus.ACTIVE:
            return self._closed(state)

        sample = self.llm.complete(system=prompts.SAMPLE, user=text, schema=SampleReply)
        if not sample.slots:
            message = (
                sample.clarifying_question
                or "I couldn't find a schedule in that. Could you paste it again?"
            )
        else:
            state.draft, added = infer_from_sample(state.draft, sample)
            state.topic = next_topic(state.draft)
            found = "\n".join(f"• {a}" for a in added) or "• nothing new beyond what you've told me"
            message = (
                f"From the sample I found:\n{found}\n\nThese are suggestions until you confirm them.\n\n"
                + self._ask(state.draft, state.topic)
            )
        state.pending_question = message
        self.sessions.save(state)
        return AgentReply(message, state.topic, state.status, state.proposal_id)

    # ------------------------------------------------------------------

    def _load(self, onboarding_id: uuid.UUID) -> OnboardingState:
        state = self.sessions.get(onboarding_id)
        if state is None:
            raise OnboardingNotFound("onboarding session not found")
        return state

    def _closed(self, state: OnboardingState) -> AgentReply:
        message = {
            OnboardingStatus.PROPOSED: "The profile is waiting for approval. Nothing runs until it's approved.",
            OnboardingStatus.APPROVED: "This church's profile is approved and active.",
        }.get(state.status, "This onboarding is closed.")
        return AgentReply(message, state.topic, state.status, state.proposal_id)

    def _advance(self, state: OnboardingState, topic: OnboardingTopic) -> str:
        new_topic = next_topic(state.draft)
        state.topic = new_topic
        if new_topic is topic and topic is not T.REVIEW:
            return (
                f"Here's what I have so far:\n{render_section(state.draft, topic)}\n\n"
                "Anything to add or change? Say “that's all” when it's right."
            )
        return self._ask(state.draft, new_topic)

    def _ask(self, draft: ChurchProfileDraft, topic: OnboardingTopic) -> str:
        question = question_for(topic)
        if topic is T.REVIEW:
            return f"{question}\n\n{render_summary(draft)}"
        if topic in SHOW_DEFAULTS or _has_inferred(draft, topic):
            return f"{question}\n\n{render_section(draft, topic)}"
        return question

    def _user_prompt(self, state: OnboardingState, text: str) -> str:
        facts = {
            "today": datetime.now(UTC).date().isoformat(),
            "question_asked": state.pending_question,
            "current_section": current_section(state.draft, state.topic),
            **context_for(state.draft, state.topic),
        }
        return (
            f"Facts (JSON):\n{json.dumps(facts, indent=2, default=str)}\n\n"
            f"Administrator's message:\n{text}"
        )


def _has_inferred(draft: ChurchProfileDraft, topic: OnboardingTopic) -> bool:
    if topic is T.GATHERINGS:
        return any(g.inferred for g in draft.gatherings)
    if topic is T.MINISTRIES:
        return any(m.inferred for m in draft.ministries)
    if topic is T.ROLES:
        return any(r.inferred for m in draft.ministries for r in m.roles)
    return False


def current_section(draft: ChurchProfileDraft, topic: OnboardingTopic) -> Any:
    """The section in the same shape the model must return it."""
    match topic:
        case T.BASICS:
            return {"timezone": draft.timezone, "language": draft.language}
        case T.GATHERINGS:
            return [
                {
                    "name": g.name,
                    "kind": g.kind,
                    "weekday": g.weekday,
                    "date": g.one_off_date.isoformat() if g.one_off_date else None,
                    "start_time": g.local_start_time.strftime("%H:%M"),
                    "duration_minutes": g.duration_minutes,
                }
                for g in draft.gatherings
            ]
        case T.MINISTRIES:
            return [{"name": m.name, "aliases": m.aliases} for m in draft.ministries]
        case T.ROLES:
            return [
                {
                    "ministry": m.name,
                    "name": r.name,
                    "minimums": [x.model_dump() for x in r.minimums],
                }
                for m in draft.ministries
                for r in m.roles
            ]
        case T.LEADERS:
            return [
                {"ministry": m.name, **x.model_dump()} for m in draft.ministries for x in m.leaders
            ]
        case T.LOAD_RULES:
            return {
                "load_rules": [r.model_dump() for r in draft.load_rules],
                "absence_threshold_weeks": draft.absence_threshold_weeks,
            }
        case T.ROUTING:
            return [r.model_dump(mode="json") for r in draft.routing]
        case T.ROSTER_SETTINGS:
            return [
                {
                    "ministry": m.name,
                    "show_both_paths": m.show_both_paths,
                    "default_path": m.default_path,
                    "draft_horizon_weeks": m.draft_horizon_weeks,
                }
                for m in draft.ministries
            ]
        case T.AVAILABILITY:
            return [
                {
                    "leader": a.leader,
                    "weekday": a.weekday,
                    "start": a.start.strftime("%H:%M"),
                    "end": a.end.strftime("%H:%M"),
                }
                for a in draft.availability
            ]
        case T.REVIEW:
            return render_summary(draft)


def context_for(draft: ChurchProfileDraft, topic: OnboardingTopic) -> dict[str, Any]:
    """Names the model may refer to (it must not invent others)."""
    ministries = [m.name for m in draft.ministries]
    if topic is T.ROLES:
        return {"ministries": ministries, "gatherings": [g.name for g in draft.gatherings]}
    if topic in (T.LEADERS, T.ROSTER_SETTINGS):
        return {"ministries": ministries}
    if topic is T.AVAILABILITY:
        return {"leaders": all_leaders(draft)}
    return {}
