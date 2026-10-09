"""One simple roster suggestion (brief §4, without the training/veteran split yet). Pure.

Hard rules, never broken:
* only active team members who have that role, and who haven't stopped;
* nobody on a blockout date;
* nobody at a time that overlaps another assignment, existing or drafted, in any
  ministry, on any day.

Preferences, weighed (rule 8, warnings not blocks): stay within the person's own
preferred frequency and the church's usual load, spread serving around (fewest
times this period first), and their preferred gathering. A slot nobody can fill
stays empty and says so; a slot that can only be filled by going over someone's
preference is filled and marked.
"""

import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from app.domain.enums import Experience, Period
from app.services.profile import format_time

EXPERIENCE_RANK = {Experience.VETERAN: 0, Experience.EXPERIENCED: 1, Experience.NEW: 2}
ALTERNATIVES = 3


@dataclass(frozen=True)
class Position:
    """One open place for one role at one gathering."""

    gathering_id: uuid.UUID
    gathering_type_id: uuid.UUID
    gathering_name: str
    start: datetime  # UTC
    end: datetime  # UTC
    local_start: datetime  # church time
    role_id: uuid.UUID
    role_name: str


@dataclass(frozen=True)
class Candidate:
    person_id: uuid.UUID
    name: str
    roles: dict[uuid.UUID, Experience]  # role id -> experience in that role


@dataclass
class DraftFacts:
    candidates: list[Candidate]
    busy: dict[uuid.UUID, list[tuple[datetime, datetime]]]  # existing assignments, any ministry
    blockouts: dict[uuid.UUID, list[tuple[date, date]]]
    served: dict[tuple[uuid.UUID, date], int]  # (person, period start) -> existing count
    period: Period  # the church's load period (month if none)
    usual: int | None  # church's normal_max for that period
    preferred: dict[uuid.UUID, tuple[int, Period]]
    preferred_gatherings: dict[uuid.UUID, set[uuid.UUID]] = field(default_factory=dict)


@dataclass(frozen=True)
class Alternative:
    person_id: uuid.UUID
    name: str
    experience: Experience


@dataclass(frozen=True)
class DraftLine:
    position: Position
    person_id: uuid.UUID | None
    name: str | None
    experience: Experience | None
    reason: str
    flags: list[str]
    alternatives: list[Alternative]


def period_start(day: date, period: Period) -> date:
    if period is Period.WEEK:
        return day - timedelta(days=(day.weekday() + 1) % 7)  # Sunday-to-Saturday church week
    return day.replace(day=1)


def draft(positions: list[Position], facts: DraftFacts) -> list[DraftLine]:
    busy = {p: list(slots) for p, slots in facts.busy.items()}
    served: dict[tuple[uuid.UUID, date], int] = defaultdict(int, facts.served)
    lines: list[DraftLine] = []

    for pos in sorted(positions, key=lambda p: (p.start, p.role_name)):
        day = pos.local_start.date()
        bucket = period_start(day, facts.period)
        eligible = [
            c
            for c in facts.candidates
            if pos.role_id in c.roles
            and not _overlaps(busy.get(c.person_id, []), pos.start, pos.end)
            and not any(a <= day <= b for a, b in facts.blockouts.get(c.person_id, []))
        ]
        ranked = sorted(eligible, key=lambda c: _score(c, pos, bucket, served, facts))
        if not ranked:
            lines.append(
                DraftLine(
                    pos,
                    None,
                    None,
                    None,
                    f"{pos.local_start:%b %-d} {pos.role_name}: no one free on your team.",
                    [],
                    [],
                )
            )
            continue

        chosen = ranked[0]
        count = served[(chosen.person_id, bucket)] + 1
        served[(chosen.person_id, bucket)] = count
        busy.setdefault(chosen.person_id, []).append((pos.start, pos.end))
        lines.append(
            DraftLine(
                position=pos,
                person_id=chosen.person_id,
                name=chosen.name,
                experience=chosen.roles[pos.role_id],
                reason=_reason(chosen, pos, count, facts),
                flags=_flags(chosen, count, facts),
                alternatives=[
                    Alternative(c.person_id, c.name, c.roles[pos.role_id])
                    for c in ranked[1 : 1 + ALTERNATIVES]
                ],
            )
        )
    return lines


def _overlaps(slots: list[tuple[datetime, datetime]], start: datetime, end: datetime) -> bool:
    return any(s < end and start < e for s, e in slots)


def _score(
    c: Candidate,
    pos: Position,
    bucket: date,
    served: dict[tuple[uuid.UUID, date], int],
    facts: DraftFacts,
) -> tuple[int, int, int, int, str]:
    count = served[(c.person_id, bucket)]
    over = _over_preference(c.person_id, count + 1, facts) or (
        facts.usual is not None and count + 1 > facts.usual
    )
    not_preferred = (
        0 if pos.gathering_type_id in facts.preferred_gatherings.get(c.person_id, set()) else 1
    )
    return (int(over), count, not_preferred, EXPERIENCE_RANK[c.roles[pos.role_id]], c.name)


def _over_preference(person_id: uuid.UUID, count: int, facts: DraftFacts) -> bool:
    pref = facts.preferred.get(person_id)
    return pref is not None and pref[1] is facts.period and count > pref[0]


def _reason(c: Candidate, pos: Position, count: int, facts: DraftFacts) -> str:
    first = c.name.split()[0]
    when = "this week" if facts.period is Period.WEEK else "this month"
    if pos.gathering_type_id in facts.preferred_gatherings.get(c.person_id, set()):
        return f"{first} prefers the {pos.gathering_name}, and is free then."
    if count == 1:
        return f"{first} is free and hasn't served yet {when}."
    return f"{first} is free; this would be {_times(count)} {when}, the fewest on the team."


def _flags(c: Candidate, count: int, facts: DraftFacts) -> list[str]:
    first = c.name.split()[0]
    when = "this week" if facts.period is Period.WEEK else "this month"
    pref = facts.preferred.get(c.person_id)
    flags = []
    if pref is not None and pref[1] is facts.period and count > pref[0]:
        flags.append(f"Above preference: {first}, {_times(count)} {when} (prefers {pref[0]})")
    elif facts.usual is not None and count > facts.usual:
        flags.append(f"Above usual: {first}, {_times(count)} {when} (usual is {facts.usual})")
    return flags


def _times(n: int) -> str:
    return {1: "once", 2: "twice"}.get(n, f"{n} times")


def describe_time(pos: Position) -> str:
    return f"{pos.local_start:%a %-d %b} {format_time(pos.local_start.time())}"
