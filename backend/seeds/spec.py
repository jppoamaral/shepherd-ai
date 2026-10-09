"""Declarative shapes for seed data. Pure data; the loader turns these into rows."""

from dataclasses import dataclass, field
from datetime import date, time, timedelta

from app.domain.enums import Experience, GatheringKind, MemoryKind, MemorySource, Period, Weekday


@dataclass(frozen=True)
class GatheringTypeSeed:
    key: str
    name: str
    local_start_time: time
    duration_minutes: int
    weekday: Weekday | None = None
    one_off_date: date | None = None
    kind: GatheringKind = GatheringKind.REGULAR


@dataclass(frozen=True)
class RoleSeed:
    name: str
    minimums: dict[str, int]  # gathering type key -> minimum people


@dataclass(frozen=True)
class LeaderSeed:
    person: str  # person key
    can_schedule: bool
    can_approve: bool


@dataclass(frozen=True)
class MinistrySeed:
    name: str
    roles: list[RoleSeed]
    leaders: list[LeaderSeed]
    aliases: list[str] = field(default_factory=list)
    draft_horizon_weeks: int = 4
    # Share of generated volunteers who join this ministry.
    weight: float = 1.0


@dataclass(frozen=True)
class AvailabilitySeed:
    weekday: Weekday
    start: time
    end: time


@dataclass(frozen=True)
class BlockoutSeed:
    """Relative to the seed's `today` (or to the demo Sunday), inclusive."""

    start_offset_days: int
    end_offset_days: int
    from_demo_sunday: bool = False

    def dates(self, today: date) -> tuple[date, date]:
        base = demo_sunday(today) if self.from_demo_sunday else today
        return (
            base + timedelta(days=self.start_offset_days),
            base + timedelta(days=self.end_offset_days),
        )


def demo_sunday(today: date) -> date:
    """The demo week starts at the first upcoming Sunday (today, if it is Sunday)."""
    return today + timedelta(days=(6 - today.weekday()) % 7)


@dataclass(frozen=True)
class PersonSeed:
    key: str
    name: str
    nicknames: list[str] = field(default_factory=list)
    # ministry name -> role name -> experience (set by that ministry's scheduler)
    skills: dict[str, dict[str, Experience]] = field(default_factory=dict)
    preferred_frequency: tuple[int, Period] | None = None
    preferred_gatherings: list[str] = field(default_factory=list)  # gathering type keys
    blockouts: list[BlockoutSeed] = field(default_factory=list)
    availability: list[AvailabilitySeed] = field(default_factory=list)  # leaders only
    opted_in: bool = True


@dataclass(frozen=True)
class AssignmentSeed:
    """An already-approved assignment at the first upcoming occurrence of a gathering type."""

    person: str
    ministry: str
    role: str
    gathering_type: str


@dataclass(frozen=True)
class MemorySeed:
    ministry: str
    kind: MemoryKind
    text: str
    proposed_from: MemorySource
    about: str | None = None  # person key
    confirmed_by: str | None = None  # person key; None = still pending ("Should I remember this?")


@dataclass(frozen=True)
class ChurchSeed:
    name: str
    timezone: str
    member_count: int
    absence_threshold_weeks: int
    load_rules: list[tuple[Period, int, int]]  # (period, normal_max, warning_above)
    gathering_types: list[GatheringTypeSeed]
    ministries: list[MinistrySeed]
    people: list[PersonSeed]
    generated_volunteers: int
    random_seed: int
    assignments: list[AssignmentSeed] = field(default_factory=list)
    generated_preferences: list[tuple[int, Period]] = field(default_factory=list)
    warning_routing: dict[str, list[str]] = field(default_factory=dict)
    memories: list[MemorySeed] = field(default_factory=list)
    # (ministry, gathering type key): fill the rest of that roster in the demo week from
    # the team, so the demo's warnings are the seeded stories rather than empty slots.
    fill_rosters: list[tuple[str, str]] = field(default_factory=list)
