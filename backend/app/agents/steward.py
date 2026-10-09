"""Steward agent: keeps the record current. In M3: schedule intake.

A scheduler pastes their roster in any format. The model reads it into entries
and, only for names code can't place, suggests possible nicknames. Code
(`app.services.intake`) resolves gatherings, roles and names, and turns
everything unclear into questions the scheduler answers by picking a choice.
When nothing is left to ask, the agent proposes a `leader_roster`; only
ApprovalService records it (rule 1). The pasted text is never stored.
"""

import json
import uuid
from dataclasses import dataclass, replace
from datetime import date

from sqlalchemy.orm import Session

from app.db.repositories.intake import IntakeRepository, IntakeState
from app.db.repositories.proposals import ProposalRepository
from app.db.repositories.reads import ChurchReader
from app.domain.enums import IntakeStatus
from app.domain.intake import (
    IntakeContext,
    IntakeQuestion,
    NicknameSuggestions,
    ParsedSchedule,
)
from app.llm.client import LLMClient
from app.llm.prompts import intake as prompts
from app.services.intake import (
    apply_answer,
    assignments,
    build_intake,
    is_ready,
    render_intake,
    unknown_names,
)
from app.services.name_matching import normalize

AGENT_NAME = "steward"
ROSTER_PROPOSAL = "leader_roster"


class IntakeNotFound(LookupError):
    pass


class IntakeNotAllowed(PermissionError):
    pass


class IntakeUnreadable(ValueError):
    """The text couldn't be read as a schedule. The message is a question for the leader."""


@dataclass(frozen=True)
class IntakeView:
    id: uuid.UUID
    ministry_id: uuid.UUID
    status: IntakeStatus
    questions: list[IntakeQuestion]
    summary: str
    proposal_id: uuid.UUID | None


class StewardAgent:
    def __init__(
        self, session: Session, church_id: uuid.UUID, llm: LLMClient, today: date | None = None
    ) -> None:
        self.llm = llm
        self.today = today
        self.reader = ChurchReader(session, church_id)
        self.intakes = IntakeRepository(session, church_id)
        self.proposals = ProposalRepository(session, church_id)

    def intake_schedule(
        self, ministry_id: uuid.UUID, person_id: uuid.UUID, text: str
    ) -> IntakeView:
        ctx = self.reader.intake_context(ministry_id, self.today)
        if ctx is None:
            raise IntakeNotFound("ministry not found")
        self._require_scheduler(ministry_id, person_id)

        parsed = self.llm.complete(
            system=prompts.PARSE, user=_parse_prompt(ctx, text), schema=ParsedSchedule
        )
        if not parsed.entries:
            raise IntakeUnreadable(
                parsed.clarifying_question
                or "I couldn't find a schedule in that. Could you paste it again?"
            )
        ctx = self._with_suggestions(ctx, unknown_names(parsed.entries, ctx))
        state = self.intakes.create(
            ministry_id=ministry_id,
            submitted_by_person_id=person_id,
            draft=build_intake(parsed.entries, ctx),
        )
        self._propose_if_ready(state)
        return _view(state)

    def answer(
        self, intake_id: uuid.UUID, person_id: uuid.UUID, question_id: str, choice_id: str
    ) -> IntakeView:
        state = self._load(intake_id)
        self._require_scheduler(state.ministry_id, person_id)
        if state.status is not IntakeStatus.NEEDS_ANSWERS:
            raise IntakeNotAllowed(
                f"this schedule is already {state.status.value.replace('_', ' ')}"
            )
        state.draft = apply_answer(state.draft, question_id, choice_id)
        self._propose_if_ready(state)
        self.intakes.save(state)
        return _view(state)

    def view(self, intake_id: uuid.UUID) -> IntakeView:
        return _view(self._load(intake_id))

    # ------------------------------------------------------------------

    def _load(self, intake_id: uuid.UUID) -> IntakeState:
        state = self.intakes.get(intake_id)
        if state is None:
            raise IntakeNotFound("schedule intake not found")
        return state

    def _require_scheduler(self, ministry_id: uuid.UUID, person_id: uuid.UUID) -> None:
        leader = self.reader.ministry_leader(ministry_id, person_id)
        if leader is None or not leader.can_schedule:
            raise IntakeNotAllowed(
                "only this ministry's scheduler can submit or answer its schedule"
            )

    def _with_suggestions(self, ctx: IntakeContext, unknown: list[str]) -> IntakeContext:
        if not unknown:
            return ctx
        facts = {"team": [p.name for p in ctx.team], "names": unknown}
        reply = self.llm.complete(
            system=prompts.SUGGEST,
            user=f"Facts (JSON):\n{json.dumps(facts, indent=2)}",
            schema=NicknameSuggestions,
        )
        # Keep only real team members; the model can suggest, never invent.
        team = {p.name.casefold(): p.id for p in ctx.team}
        suggestions = {
            normalize(s.name_as_written): tuple(
                dict.fromkeys(team[c.casefold()] for c in s.candidates if c.casefold() in team)
            )
            for s in reply.suggestions
        }
        return replace(ctx, suggestions=suggestions)

    def _propose_if_ready(self, state: IntakeState) -> None:
        if state.status is not IntakeStatus.NEEDS_ANSWERS or not is_ready(state.draft):
            return
        proposal = self.proposals.create(
            type=ROSTER_PROPOSAL,
            payload={
                "ministry_id": str(state.ministry_id),
                "intake_id": str(state.id),
                "assignments": [
                    {
                        "gathering_id": str(a.gathering_id),
                        "role_id": str(a.role_id),
                        "person_id": str(a.person_id),
                    }
                    for a in assignments(state.draft)
                ],
                "nicknames": [n.model_dump(mode="json") for n in state.draft.nicknames],
            },
            created_by_agent=AGENT_NAME,
        )
        state.status, state.proposal_id = IntakeStatus.PROPOSED, proposal.id
        self.intakes.save(state)


def _parse_prompt(ctx: IntakeContext, text: str) -> str:
    upcoming = [g for g in ctx.gatherings if g.local_date >= ctx.today][:30]
    facts = {
        "today": ctx.today.isoformat(),
        "ministry": ctx.ministry_name,
        "roles": [r.name for r in ctx.roles],
        "upcoming_gatherings": [f"{g.name}: {g.local_start:%a %Y-%m-%d %H:%M}" for g in upcoming],
    }
    return f"Facts (JSON):\n{json.dumps(facts, indent=2)}\n\nPasted schedule:\n{text}"


def _view(state: IntakeState) -> IntakeView:
    return IntakeView(
        id=state.id,
        ministry_id=state.ministry_id,
        status=state.status,
        questions=state.draft.questions,
        summary=render_intake(state.draft),
        proposal_id=state.proposal_id,
    )
