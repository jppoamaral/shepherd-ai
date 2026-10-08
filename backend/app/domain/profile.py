"""The church profile as onboarding builds it, and the model's structured replies.

Two families of types live here:

* `ChurchProfileDraft` and its parts: the validated draft that code owns. Items
  are keyed by name because nothing has a database id until the profile is
  approved and applied.
* `*Reply` / `Sample*`: what the language model returns. They use plain strings
  for dates and times ("2026-12-24", "19:30") and lists instead of maps, so they
  work with strict structured outputs; code parses and validates them.
"""

from datetime import date, time

from pydantic import BaseModel, Field, field_validator, model_validator

from app.domain.enums import (
    FindingType,
    GatheringKind,
    OnboardingTopic,
    Period,
    Recipient,
    Recurrence,
    RosterPath,
    Weekday,
)

MAX_DURATION_MINUTES = 12 * 60


# ---------------------------------------------------------------------------
# The draft (owned by code)
# ---------------------------------------------------------------------------


class DraftGathering(BaseModel):
    name: str
    kind: GatheringKind = GatheringKind.REGULAR
    recurrence: Recurrence
    weekday: Weekday | None = None
    one_off_date: date | None = None
    local_start_time: time
    duration_minutes: int = Field(gt=0, le=MAX_DURATION_MINUTES)
    # Came from a sample schedule and still needs the admin's confirmation.
    inferred: bool = False

    @model_validator(mode="after")
    def recurrence_fields(self) -> "DraftGathering":
        if self.recurrence is Recurrence.WEEKLY and (self.weekday is None or self.one_off_date):
            raise ValueError(f"{self.name}: a weekly gathering needs a weekday and no date")
        if self.recurrence is Recurrence.ONE_OFF and (self.one_off_date is None or self.weekday):
            raise ValueError(f"{self.name}: a one-off event needs a date and no weekday")
        return self


class DraftRoleMinimum(BaseModel):
    gathering: str  # DraftGathering.name
    minimum: int = Field(ge=0)


class DraftRole(BaseModel):
    name: str
    minimums: list[DraftRoleMinimum] = []
    inferred: bool = False


class DraftLeader(BaseModel):
    name: str
    can_schedule: bool
    can_approve: bool

    @model_validator(mode="after")
    def has_a_duty(self) -> "DraftLeader":
        if not (self.can_schedule or self.can_approve):
            raise ValueError(f"{self.name} must schedule, approve, or both")
        return self


class DraftMinistry(BaseModel):
    name: str
    aliases: list[str] = []
    roles: list[DraftRole] = []
    leaders: list[DraftLeader] = []
    show_both_paths: bool = True
    default_path: RosterPath = RosterPath.TRAINING
    draft_horizon_weeks: int = Field(default=4, ge=1, le=52)
    inferred: bool = False


class DraftLoadRule(BaseModel):
    period: Period
    normal_max: int = Field(ge=0)
    warning_above: int = Field(ge=0)

    @model_validator(mode="after")
    def ordered(self) -> "DraftLoadRule":
        if self.warning_above < self.normal_max:
            raise ValueError("the warning level can't be below the normal level")
        return self


class DraftAvailability(BaseModel):
    leader: str  # DraftLeader.name
    weekday: Weekday
    start: time
    end: time

    @model_validator(mode="after")
    def ordered(self) -> "DraftAvailability":
        if self.end <= self.start:
            raise ValueError(f"{self.leader}: a window must end after it starts")
        return self


class DraftRoute(BaseModel):
    finding: FindingType
    recipients: list[Recipient]


def default_routing() -> list[DraftRoute]:
    """Brief section 5, offered to the admin to confirm or change."""
    s, a = Recipient.SCHEDULER, Recipient.APPROVER
    return [
        DraftRoute(finding=FindingType.OVERLAP, recipients=[s, a]),
        DraftRoute(finding=FindingType.BLOCKOUT, recipients=[s]),
        DraftRoute(finding=FindingType.BELOW_MINIMUM, recipients=[s]),
        DraftRoute(finding=FindingType.LOAD, recipients=[a]),
        DraftRoute(finding=FindingType.ABSENT, recipients=[a]),
        DraftRoute(finding=FindingType.SILENT_MINISTRY, recipients=[a]),
        DraftRoute(finding=FindingType.UNMATCHED_NAME, recipients=[s]),
    ]


class ChurchProfileDraft(BaseModel):
    timezone: str | None = None
    language: str = "en"
    gatherings: list[DraftGathering] = []
    ministries: list[DraftMinistry] = []
    load_rules: list[DraftLoadRule] = []
    absence_threshold_weeks: int | None = Field(default=None, ge=1, le=52)
    routing: list[DraftRoute] = Field(default_factory=default_routing)
    availability: list[DraftAvailability] = []
    # Topics the admin has confirmed ("that's right"). Order lives in OnboardingTopic.
    confirmed: list[OnboardingTopic] = []

    @field_validator("confirmed")
    @classmethod
    def unique_topics(cls, value: list[OnboardingTopic]) -> list[OnboardingTopic]:
        return list(dict.fromkeys(value))


# ---------------------------------------------------------------------------
# Language-model replies (one per topic). Each returns the WHOLE section as the
# admin now wants it, plus whether they said the section is done, plus a
# clarifying question when the answer was ambiguous (then nothing is applied).
# ---------------------------------------------------------------------------


class ReplyBase(BaseModel):
    topic_done: bool = Field(
        description="True only if the admin said this section is complete and correct."
    )
    clarifying_question: str | None = Field(
        description="One short question when the answer is ambiguous. If set, no changes are applied."
    )


class BasicsReply(ReplyBase):
    timezone: str | None = Field(description="IANA time zone, e.g. America/Chicago")
    language: str | None = Field(description="ISO 639-1 language code, e.g. en")


class GatheringIn(BaseModel):
    name: str
    previous_name: str | None = Field(
        default=None,
        description="If this renames an item in current_section, that item's old name; otherwise null",
    )
    kind: GatheringKind
    weekday: Weekday | None = Field(description="For weekly gatherings; null for one-off events")
    date: str | None = Field(description="YYYY-MM-DD for one-off events; null for weekly")
    start_time: str = Field(description="24-hour HH:MM in the church's local time")
    duration_minutes: int


class GatheringsReply(ReplyBase):
    gatherings: list[GatheringIn]


class MinistryIn(BaseModel):
    name: str
    previous_name: str | None = Field(
        default=None,
        description="If this renames an item in current_section, that item's old name; otherwise null",
    )
    aliases: list[str]


class MinistriesReply(ReplyBase):
    ministries: list[MinistryIn]


class RoleMinimumIn(BaseModel):
    gathering: str
    minimum: int


class RoleIn(BaseModel):
    ministry: str
    name: str
    minimums: list[RoleMinimumIn]


class RolesReply(ReplyBase):
    roles: list[RoleIn]


class LeaderIn(BaseModel):
    ministry: str
    name: str
    can_schedule: bool
    can_approve: bool


class LeadersReply(ReplyBase):
    leaders: list[LeaderIn]


class LoadRuleIn(BaseModel):
    period: Period
    normal_max: int
    warning_above: int


class LoadRulesReply(ReplyBase):
    load_rules: list[LoadRuleIn]
    absence_threshold_weeks: int | None = Field(
        description="Weeks without serving before the approver hears about it; null if not said"
    )


class RoutingReply(ReplyBase):
    routing: list[DraftRoute]


class RosterSettingIn(BaseModel):
    ministry: str
    show_both_paths: bool
    default_path: RosterPath
    draft_horizon_weeks: int


class RosterSettingsReply(ReplyBase):
    settings: list[RosterSettingIn]


class AvailabilityIn(BaseModel):
    leader: str
    weekday: Weekday
    start: str = Field(description="HH:MM")
    end: str = Field(description="HH:MM")


class AvailabilityReply(ReplyBase):
    availability: list[AvailabilityIn]


class ReviewReply(ReplyBase):
    """At review, `topic_done` means the admin approves the summary as shown."""

    change_topic: OnboardingTopic | None = Field(
        description="If the admin wants to change something, the section it belongs to"
    )


TopicReply = (
    BasicsReply
    | GatheringsReply
    | MinistriesReply
    | RolesReply
    | LeadersReply
    | LoadRulesReply
    | RoutingReply
    | RosterSettingsReply
    | AvailabilityReply
    | ReviewReply
)

REPLY_SCHEMAS: dict[OnboardingTopic, type[ReplyBase]] = {
    OnboardingTopic.BASICS: BasicsReply,
    OnboardingTopic.GATHERINGS: GatheringsReply,
    OnboardingTopic.MINISTRIES: MinistriesReply,
    OnboardingTopic.ROLES: RolesReply,
    OnboardingTopic.LEADERS: LeadersReply,
    OnboardingTopic.LOAD_RULES: LoadRulesReply,
    OnboardingTopic.ROUTING: RoutingReply,
    OnboardingTopic.ROSTER_SETTINGS: RosterSettingsReply,
    OnboardingTopic.AVAILABILITY: AvailabilityReply,
    OnboardingTopic.REVIEW: ReviewReply,
}


# ---------------------------------------------------------------------------
# Sample schedules. The model reads a pasted schedule into rows; it reports how
# many people filled each role, never who, so no names leave the parser.
# ---------------------------------------------------------------------------


class SampleSlot(BaseModel):
    date: str | None = Field(description="YYYY-MM-DD if the schedule shows it")
    weekday: Weekday | None
    start_time: str | None = Field(description="24-hour HH:MM if shown")
    gathering: str | None = Field(description="The gathering's name as written, if any")
    ministry: str
    role: str
    people_count: int


class SampleReply(BaseModel):
    slots: list[SampleSlot]
    clarifying_question: str | None
