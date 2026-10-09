"""Read-side API shapes. Pydantic only; no I/O."""

import uuid
from datetime import date, datetime, time
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domain.enums import (
    AskIntent,
    AssignmentStatus,
    Experience,
    FindingStatus,
    FindingType,
    GatheringKind,
    HuddleStatus,
    IntakeStatus,
    MembershipStatus,
    MemoryKind,
    MemorySource,
    OnboardingStatus,
    OnboardingTopic,
    Period,
    ProfileStatus,
    ProposalStatus,
    Recurrence,
    RosterPath,
    Weekday,
)
from app.domain.intake import IntakeQuestion


class Schema(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class LoadRuleOut(Schema):
    period: Period
    normal_max: int
    warning_above: int


class ChurchOut(Schema):
    id: uuid.UUID
    name: str
    timezone: str
    language: str
    profile_status: ProfileStatus
    member_count: int | None
    load_rules: list[LoadRuleOut]


class GatheringTypeOut(Schema):
    id: uuid.UUID
    name: str
    kind: GatheringKind
    recurrence: Recurrence
    weekday: Weekday | None
    one_off_date: date | None
    local_start_time: time
    duration_minutes: int


class RoleMinimumOut(Schema):
    gathering_type_id: uuid.UUID
    minimum: int


class RoleOut(Schema):
    id: uuid.UUID
    name: str
    minimums: list[RoleMinimumOut]


class LeaderOut(Schema):
    person_id: uuid.UUID
    name: str
    can_schedule: bool
    can_approve: bool


class MinistryOut(Schema):
    id: uuid.UUID
    name: str
    aliases: list[str]
    show_both_paths: bool
    default_path: RosterPath
    draft_horizon_weeks: int
    roles: list[RoleOut]
    leaders: list[LeaderOut]


class RoleSkillOut(Schema):
    role_id: uuid.UUID
    role: str
    experience: Experience


class MembershipOut(Schema):
    ministry_id: uuid.UUID
    ministry: str
    status: MembershipStatus
    last_served: date | None
    roles: list[RoleSkillOut]


class PersonOut(Schema):
    id: uuid.UUID
    name: str
    nicknames: list[str]
    opted_in: bool
    stopped: bool
    memberships: list[MembershipOut]


class GatheringOut(Schema):
    id: uuid.UUID
    gathering_type_id: uuid.UUID
    name: str
    kind: GatheringKind
    start_at: datetime  # in the church's time zone, with offset
    end_at: datetime


class ProposalOut(Schema):
    id: uuid.UUID
    type: str
    status: ProposalStatus
    created_by_agent: str
    created_at: datetime
    decided_by_person_id: uuid.UUID | None
    decided_at: datetime | None
    payload: dict[str, Any]
    # Plain language for the approval queue, filled in by the API.
    title: str = ""
    summary: str = ""
    # Reminders: how many will actually be sent (people whose place changed are left out).
    count: int | None = None


class OnboardingStart(BaseModel):
    church_name: str = Field(min_length=1, max_length=200)
    admin_name: str = Field(min_length=1, max_length=200)


class OnboardingStarted(BaseModel):
    onboarding_id: uuid.UUID
    church_id: uuid.UUID
    admin_person_id: uuid.UUID
    topic: OnboardingTopic
    message: str


class ChatIn(BaseModel):
    text: str = Field(min_length=1, max_length=20_000)


class AgentReplyOut(BaseModel):
    message: str
    topic: OnboardingTopic
    status: OnboardingStatus
    proposal_id: uuid.UUID | None


class OnboardingOut(BaseModel):
    id: uuid.UUID
    status: OnboardingStatus
    topic: OnboardingTopic
    pending_question: str | None
    proposal_id: uuid.UUID | None
    summary: str


class DecisionIn(BaseModel):
    person_id: uuid.UUID


class IntakeSubmit(BaseModel):
    person_id: uuid.UUID
    text: str = Field(min_length=1, max_length=50_000)


class IntakeAnswer(BaseModel):
    person_id: uuid.UUID
    question_id: str
    choice_id: str


class IntakeOut(BaseModel):
    id: uuid.UUID
    ministry_id: uuid.UUID
    status: IntakeStatus
    questions: list[IntakeQuestion]
    summary: str
    proposal_id: uuid.UUID | None


class LeaderMinistry(BaseModel):
    ministry_id: uuid.UUID
    ministry: str
    can_schedule: bool
    can_approve: bool


class LeaderSummary(BaseModel):
    """For the demo's "who am I" picker (no auth yet)."""

    person_id: uuid.UUID
    name: str
    ministries: list[LeaderMinistry]


class BriefingItem(BaseModel):
    finding_id: uuid.UUID
    type: FindingType
    severity: str  # "warning" | "noted"
    text: str
    on: date
    ministries: list[str]
    people: list[str]
    # A double booking shared with another ministry's leader: offer "Find a time to talk".
    can_huddle: bool
    # An open slot: who on the team is free to fill it (the leader decides).
    fill: "GapFill | None" = None


class GapFill(BaseModel):
    ministry_id: uuid.UUID
    gathering_id: uuid.UUID
    role_id: uuid.UUID
    role: str
    person_id: uuid.UUID
    name: str
    experience: Experience


class BriefingGathering(BaseModel):
    gathering_id: uuid.UUID
    ministry_id: uuid.UUID
    ministry: str
    name: str
    start_at: datetime
    needed: int
    filled: int


class BriefingOut(BaseModel):
    person_id: uuid.UUID
    name: str
    start: date
    end: date  # exclusive
    headline: str
    items: list[BriefingItem]
    gatherings: list[BriefingGathering]


class RosterPerson(BaseModel):
    assignment_id: uuid.UUID
    person_id: uuid.UUID
    name: str
    status: AssignmentStatus
    experience: Experience | None
    flags: list[str]  # "double_booked", "over_load", "above_preference"


class RosterRole(BaseModel):
    role_id: uuid.UUID
    role: str
    minimum: int
    people: list[RosterPerson]
    missing: int


class RosterGathering(BaseModel):
    gathering_id: uuid.UUID
    name: str
    kind: GatheringKind
    start_at: datetime
    end_at: datetime
    roles: list[RosterRole]


class RosterOut(BaseModel):
    ministry_id: uuid.UUID
    ministry: str
    start: date
    end: date
    gatherings: list[RosterGathering]


class HuddleLeader(BaseModel):
    person_id: uuid.UUID
    name: str


class HuddleSlot(BaseModel):
    id: str
    start: datetime
    end: datetime
    label: str


class HuddleSide(BaseModel):
    ministry: str
    # Optional so agendas saved before these fields existed still load.
    ministry_id: uuid.UUID | None = None
    role: str
    gathering: str
    leader: str
    replacement: str | None  # one suggestion from that leader's own team; the leaders decide
    replacement_person_id: uuid.UUID | None = None
    replacement_note: str


class HuddleAgenda(BaseModel):
    title: str
    volunteer: str  # who the conflict is about; never invited
    overlap: str
    sides: list[HuddleSide]


class HuddleReplacement(BaseModel):
    """One leader settled the conflict by accepting Shepherd's replacement on their roster."""

    ministry_id: uuid.UUID
    ministry: str
    resolved_by: str
    volunteer: str
    replacement: str
    # The swap can still be undone: the assignment is still the replacement's.
    can_undo: bool


class HuddleOut(BaseModel):
    id: uuid.UUID
    finding_id: uuid.UUID
    status: HuddleStatus
    leaders: list[HuddleLeader]
    slots: list[HuddleSlot]
    chosen_slot: HuddleSlot | None
    no_common_slot: bool
    nearest_options: list[str]
    agenda: HuddleAgenda
    agenda_text: str
    outcome: str | None
    finding_status: FindingStatus
    replacement: HuddleReplacement | None = None


class HuddleStart(BaseModel):
    person_id: uuid.UUID


class HuddleChoose(BaseModel):
    person_id: uuid.UUID
    slot_id: str


class HuddleAcceptReplacement(BaseModel):
    person_id: uuid.UUID
    ministry_id: uuid.UUID  # whose side's suggestion to accept; must be the leader's own


class HuddleUndoReplacement(BaseModel):
    person_id: uuid.UUID


class HuddleResolve(BaseModel):
    person_id: uuid.UUID
    outcome: str = Field(min_length=1, max_length=2_000)


class MemoryItemOut(BaseModel):
    id: uuid.UUID
    kind: MemoryKind
    text: str
    about: str | None
    proposed_from: MemorySource
    confirmed_by: str
    created_at: datetime


class MemoryPendingOut(BaseModel):
    proposal_id: uuid.UUID
    kind: MemoryKind
    text: str
    about: str | None
    question: str  # "Should I remember this?"


class MemoryOut(BaseModel):
    ministry_id: uuid.UUID
    ministry: str
    items: list[MemoryItemOut]
    pending: list[MemoryPendingOut]


class MemoryNote(BaseModel):
    """A leader's note in chat; Shepherd proposes it as a memory to confirm."""

    person_id: uuid.UUID
    text: str = Field(min_length=1, max_length=500)
    kind: MemoryKind = MemoryKind.RULE
    about_person_id: uuid.UUID | None = None


class SuggestionAlternative(BaseModel):
    person_id: uuid.UUID
    name: str
    experience: Experience


class SuggestionLine(BaseModel):
    gathering_id: uuid.UUID
    gathering: str
    start_at: datetime  # church time, with offset
    role_id: uuid.UUID
    role: str
    person_id: uuid.UUID | None  # None = nobody free; the slot stays open
    name: str | None
    experience: Experience | None
    reason: str
    flags: list[str]
    alternatives: list[SuggestionAlternative]


class SuggestionOut(BaseModel):
    ministry_id: uuid.UUID
    ministry: str
    start: date
    end: date
    lines: list[SuggestionLine]
    open: int  # positions nobody could fill


class SuggestedAssignment(BaseModel):
    gathering_id: uuid.UUID
    role_id: uuid.UUID
    person_id: uuid.UUID
    reason: str | None = None


class SuggestionApprove(BaseModel):
    person_id: uuid.UUID
    assignments: list[SuggestedAssignment] = Field(min_length=1)


# ---------------------------------------------------------------------------
# Ask Shepherd
# ---------------------------------------------------------------------------


class AskIn(BaseModel):
    """A typed question, or a tapped suggestion/action (an intent with its details)."""

    person_id: uuid.UUID  # the leader asking
    question: str | None = Field(default=None, max_length=500)
    intent: AskIntent | None = None
    about_person_id: uuid.UUID | None = None
    on: date | None = None
    role_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def _question_or_intent(self) -> "AskIn":
        if not (self.question and self.question.strip()) and self.intent is None:
            raise ValueError("ask a question or pick a suggestion")
        return self


class AskAction(BaseModel):
    """A button under an answer: ask a follow-up, or open a screen in the app."""

    label: str
    kind: Literal["ask", "link"]
    intent: AskIntent | None = None
    about_person_id: uuid.UUID | None = None
    on: date | None = None
    role_id: uuid.UUID | None = None
    href: str | None = None  # app path for links, e.g. "/huddle/<finding id>"


class AskPerson(BaseModel):
    person_id: uuid.UUID
    name: str
    experience: Experience | None
    detail: str


class AskDraft(BaseModel):
    """A 1:1 message for the leader to copy. Never stored or sent by Shepherd."""

    to_person_id: uuid.UUID
    to: str
    body: str


class AskAnswer(BaseModel):
    intent: AskIntent
    text: str
    people: list[AskPerson] = []
    notes: list[str] = []
    drafts: list[AskDraft] = []
    actions: list[AskAction] = []
    source: str | None = None  # "From ...", so the leader can check the answer
    looked_at: list[str] = []
    refused: bool = False  # "Can't help with that"


class AskStart(BaseModel):
    ministry: str
    greeting: str
    suggestions: list[AskAction]


# ---------------------------------------------------------------------------
# Volunteer chat (the demo simulator now, Telegram later) and leader notices
# ---------------------------------------------------------------------------


class ChatMessageOut(BaseModel):
    """Shepherd's side of one person's chat: approved messages and the bot's replies."""

    id: uuid.UUID
    body: str
    buttons: list[str]
    at: datetime
    approved: bool  # true for a message a leader approved; false for a bot reply


class ChatThreadOut(BaseModel):
    person_id: uuid.UUID
    name: str
    church: str
    channel: str
    messages: list[ChatMessageOut]


class ChatReplyOut(BaseModel):
    replies: list[ChatMessageOut]


class VolunteerOut(BaseModel):
    person_id: uuid.UUID
    name: str
    ministries: list[str]
    connected: bool
    stopped: bool


class NoticeOut(BaseModel):
    id: uuid.UUID
    ministry_id: uuid.UUID
    about: str
    kind: str
    text: str
    note: str | None  # the volunteer's own words, shown once
    at: datetime
    # The place it was about has since been dealt with ("Caleb Baker is in."), so it no
    # longer needs the leader; it stays until dismissed, as good to know.
    settled: bool = False
    update: str | None = None
