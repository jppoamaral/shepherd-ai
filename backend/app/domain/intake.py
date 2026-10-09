"""Schedule intake: what the model reads from a pasted roster, and what code makes of it.

* `ParsedSchedule` / `NicknameSuggestions`: model outputs (strings for dates and
  times, lists instead of maps, so they work with strict structured outputs).
* `IntakeContext`: the facts code resolves against (team, roles, gatherings).
* `IntakeDraft`: slots (one person in one role at one gathering) plus the
  questions still open. Code owns it; the leader answers by picking choices.
"""

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, time

from pydantic import BaseModel, Field

from app.domain.enums import QuestionKind, Weekday

# ---------------------------------------------------------------------------
# Model outputs
# ---------------------------------------------------------------------------


class ParsedEntry(BaseModel):
    date: str | None = Field(description="YYYY-MM-DD, resolved against today; null if not given")
    weekday: Weekday | None = Field(description="Weekday if written (e.g. 'Sun'); else null")
    time: str | None = Field(description="24-hour HH:MM if a time is written for this gathering")
    gathering: str | None = Field(
        description="Gathering name or label as written (e.g. 'prayer night', '2nd service')"
    )
    all_gatherings_that_day: bool = Field(
        description="True when the schedule says this applies to every service that day "
        "('both services', 'all services')"
    )
    role_as_written: str = Field(description="The role exactly as written, e.g. 'kb', 'chk-in'")
    role: str | None = Field(
        description="One of the provided role names if you are sure what role_as_written "
        "means; otherwise null"
    )
    names: list[str] = Field(description="People's names exactly as written, nothing else")


class ParsedSchedule(BaseModel):
    entries: list[ParsedEntry]
    clarifying_question: str | None = Field(
        description="Only if the text can't be read as a schedule at all"
    )


class NicknameSuggestion(BaseModel):
    name_as_written: str
    candidates: list[str] = Field(
        description="Full names from the team this could plausibly refer to; may be empty"
    )


class NicknameSuggestions(BaseModel):
    suggestions: list[NicknameSuggestion]


# ---------------------------------------------------------------------------
# Facts code resolves against (loaded from the record, church-scoped)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PersonRef:
    id: uuid.UUID
    name: str
    nicknames: tuple[str, ...] = ()


@dataclass(frozen=True)
class RoleRef:
    id: uuid.UUID
    name: str


@dataclass(frozen=True)
class GatheringRef:
    id: uuid.UUID
    name: str
    local_start: datetime  # in the church's time zone
    # Whether this ministry has any role minimum at this gathering's type.
    ministry_serves: bool

    @property
    def local_date(self) -> date:
        return self.local_start.date()

    @property
    def local_time(self) -> time:
        return self.local_start.time()


@dataclass(frozen=True)
class IntakeContext:
    ministry_id: uuid.UUID
    ministry_name: str
    team: tuple[PersonRef, ...]  # active members of this ministry
    others: tuple[PersonRef, ...]  # everyone else in the church
    roles: tuple[RoleRef, ...]
    gatherings: tuple[GatheringRef, ...]
    today: date
    timezone: str
    suggestions: dict[str, tuple[uuid.UUID, ...]] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# The intake draft (owned by code)
# ---------------------------------------------------------------------------


class IntakeSlot(BaseModel):
    id: int
    when: str  # as understood, for display: "Sun 11 Oct" / "10/25"
    gathering_id: uuid.UUID | None = None
    gathering_label: str | None = None
    role_as_written: str
    role_id: uuid.UUID | None = None
    role_label: str | None = None
    name_as_written: str
    person_id: uuid.UUID | None = None
    person_label: str | None = None
    left_out: bool = False

    @property
    def resolved(self) -> bool:
        return self.left_out or None not in (self.gathering_id, self.role_id, self.person_id)


class Choice(BaseModel):
    id: str
    label: str
    # The person, gathering or role this choice picks; None means "leave these slots out".
    value: uuid.UUID | None = None
    # Save the name as written as a nickname of the chosen person (on approval).
    learn_nickname: bool = False


class IntakeQuestion(BaseModel):
    id: str
    kind: QuestionKind
    subject: str  # the name, date or role text the question is about
    prompt: str
    choices: list[Choice]
    slot_ids: list[int]


class LearnedNickname(BaseModel):
    person_id: uuid.UUID
    nickname: str


class IntakeDraft(BaseModel):
    slots: list[IntakeSlot] = []
    questions: list[IntakeQuestion] = []
    nicknames: list[LearnedNickname] = []
