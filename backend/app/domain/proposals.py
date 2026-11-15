"""What each kind of proposal carries. No I/O.

A proposal's payload is stored as JSON. These models are how code builds one (`stored()`)
and reads one back (`Model.model_validate(proposal.payload)`), so the shape is written
down once. `PAYLOADS` names the model for every `ProposalType`.

Payloads hold ids, dates and message wording only; never a volunteer's own words or a
personal reason.
"""

import uuid
from datetime import date
from typing import Any, Literal

from pydantic import BaseModel

from app.domain.enums import MemoryKind, MemorySource, ProposalType
from app.domain.intake import LearnedNickname
from app.domain.profile import ChurchProfileDraft


class ProposalPayload(BaseModel):
    def stored(self) -> dict[str, Any]:
        """The JSON kept on the proposal. Fields that are None are left out."""
        return self.model_dump(mode="json", exclude_none=True)


class MinistryPayload(ProposalPayload):
    """A proposal about one ministry. Its leaders are the ones who may decide it."""

    ministry_id: uuid.UUID


# --- rosters ---------------------------------------------------------------------


class RosterLine(BaseModel):
    gathering_id: uuid.UUID
    role_id: uuid.UUID
    person_id: uuid.UUID
    reason: str | None = None


class LeaderRosterPayload(MinistryPayload):
    """A roster for one ministry: pasted by the scheduler (intake) or suggested by Shepherd
    and edited by the leader (`source="suggestion"`)."""

    intake_id: uuid.UUID | None = None
    source: Literal["suggestion"] | None = None
    assignments: list[RosterLine]
    nicknames: list[LearnedNickname] = []


# --- memory ----------------------------------------------------------------------


class MemoryPayload(MinistryPayload):
    text: str
    kind: MemoryKind
    proposed_from: MemorySource
    about_person_id: uuid.UUID | None = None


# --- messages a leader approves -----------------------------------------------------


class ReminderMessage(BaseModel):
    assignment_id: uuid.UUID
    person_id: uuid.UUID
    body: str


class RemindersPayload(MinistryPayload):
    """The 1:1 reminders for one ministry and gathering."""

    gathering_id: uuid.UUID
    messages: list[ReminderMessage]
    buttons: list[str] = []


class ServeAskMessage(BaseModel):
    person_id: uuid.UUID
    body: str
    gathering_id: uuid.UUID
    role_id: uuid.UUID
    # Set when the ask is to take a place someone else holds.
    replaces_assignment_id: uuid.UUID | None = None


class ServeAskPayload(MinistryPayload):
    messages: list[ServeAskMessage]


class ServeAskSwapPayload(MinistryPayload):
    """Someone who said yes takes over another person's place."""

    assignment_id: uuid.UUID
    from_person_id: uuid.UUID
    to_person_id: uuid.UUID


# --- huddle ----------------------------------------------------------------------


class HuddleAcceptPayload(ProposalPayload):
    huddle_id: uuid.UUID
    finding_id: uuid.UUID
    ministry_id: uuid.UUID
    ministry: str
    assignment_id: uuid.UUID
    from_person_id: uuid.UUID
    to_person_id: uuid.UUID


class HuddleUndoPayload(ProposalPayload):
    huddle_id: uuid.UUID


# --- a volunteer's own answers ------------------------------------------------------


class ReplyPayload(ProposalPayload):
    """Stop and start need nothing more than who answered."""

    person_id: uuid.UUID


class ReplyPlacePayload(ReplyPayload):
    """Yes or can't make it, for a place she was reminded about."""

    assignment_id: uuid.UUID


class ReplyAskPayload(ReplyPayload):
    """Her answer to a leader's ask to serve."""

    message_id: uuid.UUID


class ReplyAwayPayload(ReplyPayload):
    dates: list[date]


PAYLOADS: dict[ProposalType, type[BaseModel]] = {
    ProposalType.CHURCH_PROFILE: ChurchProfileDraft,
    ProposalType.LEADER_ROSTER: LeaderRosterPayload,
    ProposalType.MEMORY: MemoryPayload,
    ProposalType.REMINDERS: RemindersPayload,
    ProposalType.SERVE_ASK: ServeAskPayload,
    ProposalType.SERVE_ASK_SWAP: ServeAskSwapPayload,
    ProposalType.HUDDLE_ACCEPT_REPLACEMENT: HuddleAcceptPayload,
    ProposalType.HUDDLE_UNDO_REPLACEMENT: HuddleUndoPayload,
    ProposalType.REPLY_CONFIRM: ReplyPlacePayload,
    ProposalType.REPLY_DECLINE: ReplyPlacePayload,
    ProposalType.REPLY_AWAY: ReplyAwayPayload,
    ProposalType.REPLY_STOP: ReplyPayload,
    ProposalType.REPLY_START: ReplyPayload,
    ProposalType.REPLY_CAN_SERVE: ReplyAskPayload,
    ProposalType.REPLY_CANT_SERVE: ReplyAskPayload,
}
