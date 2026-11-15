"""Facts the deterministic checks read, and the issues they report. No I/O."""

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from app.domain.enums import FindingType, Period


@dataclass(frozen=True)
class AssignmentFact:
    id: uuid.UUID
    person_id: uuid.UUID
    person_name: str
    ministry_id: uuid.UUID
    ministry_name: str
    role_id: uuid.UUID
    role_name: str
    gathering_id: uuid.UUID
    gathering_name: str
    start: datetime  # UTC instant
    end: datetime  # UTC instant
    local_start: datetime  # church time zone, for display and week/month buckets
    local_end: datetime


@dataclass(frozen=True)
class LoadRuleFact:
    period: Period
    normal_max: int
    warning_above: int


@dataclass(frozen=True)
class PreferenceFact:
    count: int
    period: Period


@dataclass(frozen=True)
class RoleNeed:
    """One role's minimum at one gathering of a ministry that has started its roster."""

    ministry_id: uuid.UUID
    ministry_name: str
    role_id: uuid.UUID
    role_name: str
    gathering_id: uuid.UUID
    gathering_name: str
    local_start: datetime
    minimum: int
    filled: int


@dataclass(frozen=True)
class MemberFact:
    """One active team member, for the absence check."""

    membership_id: uuid.UUID
    person_id: uuid.UUID
    person_name: str
    ministry_id: uuid.UUID
    ministry_name: str
    last_served: date | None  # church-local; None = no serving on record yet
    asked_on: date | None  # when the approver last chose "Ask me later"
    upcoming: bool  # already on a coming roster for this ministry


@dataclass(frozen=True)
class Issue:
    type: FindingType
    key: str  # stable identity, so re-running checks updates instead of duplicating
    severity: str  # "warning" or "noted"
    text: str  # one deterministic plain-language line
    gathering_id: uuid.UUID | None
    person_ids: tuple[uuid.UUID, ...]
    ministry_ids: tuple[uuid.UUID, ...]
    on: str  # ISO date (church-local) the issue is about, for windowing
    details: dict[str, Any] = field(default_factory=dict)
