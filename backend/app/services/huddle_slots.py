"""Finding a short time for two leaders to talk (brief §7). Pure: no I/O.

Both leaders' weekly availability windows (church-local) are intersected on
each day between now and the gathering. Shepherd offers 2 or 3 slots of 15
minutes, spread out (one every 30 minutes, earliest first). With no common
time it says so and lists each leader's nearest windows instead.
"""

import uuid
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from app.domain.enums import Weekday
from app.services.profile import format_time

SLOT = timedelta(minutes=15)
STEP = timedelta(minutes=30)
MAX_SLOTS = 3
LEAD_TIME = timedelta(hours=1)  # don't offer a slot that starts in the next hour


@dataclass(frozen=True)
class Window:
    weekday: Weekday
    start: time
    end: time


@dataclass(frozen=True)
class Slot:
    start: datetime  # church-local, tz-aware
    end: datetime

    @property
    def label(self) -> str:
        return f"{self.start:%a %-d %b}, {format_time(self.start.time())} to {format_time(self.end.time())}"


@dataclass(frozen=True)
class NearestOption:
    person_id: uuid.UUID
    label: str


def common_slots(
    windows: dict[uuid.UUID, list[Window]], now: datetime, before: datetime
) -> list[Slot]:
    """Up to 3 fifteen-minute slots when every leader is free, after now and before `before`."""
    earliest = now + LEAD_TIME
    slots: list[Slot] = []
    for day in _days(now.date(), before.date()):
        shared = _intersect([_on(day, ws, now) for ws in windows.values()])
        for start, end in shared:
            t = start
            while t + SLOT <= end and len(slots) < MAX_SLOTS:
                if t >= earliest and t + SLOT <= before:
                    slots.append(Slot(t, t + SLOT))
                t += STEP
        if len(slots) >= MAX_SLOTS:
            break
    return slots


def nearest_options(
    windows: dict[uuid.UUID, list[Window]],
    names: dict[uuid.UUID, str],
    now: datetime,
    before: datetime,
    per_person: int = 2,
) -> list[NearestOption]:
    """Each leader's next windows, for the "no common slot" case (brief §7)."""
    horizon = max(before, now + timedelta(days=7))
    options: list[NearestOption] = []
    for person_id, ws in windows.items():
        upcoming = [
            (start, end)
            for day in _days(now.date(), horizon.date())
            for start, end in _on(day, ws, now)
            if end > now + LEAD_TIME
        ][:per_person]
        options += [
            NearestOption(
                person_id,
                f"{names[person_id]} is free {start:%a %-d %b}, "
                f"{format_time(start.time())} to {format_time(end.time())}",
            )
            for start, end in upcoming
        ]
        if not upcoming:
            options.append(
                NearestOption(person_id, f"{names[person_id]} has no availability windows set")
            )
    return options


def _days(first: date, last: date) -> list[date]:
    return [first + timedelta(days=n) for n in range((last - first).days + 1)]


def _on(day: date, windows: list[Window], now: datetime) -> list[tuple[datetime, datetime]]:
    tz = now.tzinfo
    return sorted(
        (datetime.combine(day, w.start, tzinfo=tz), datetime.combine(day, w.end, tzinfo=tz))
        for w in windows
        if w.weekday.number == day.weekday()
    )


def _intersect(
    per_person: list[list[tuple[datetime, datetime]]],
) -> list[tuple[datetime, datetime]]:
    if not per_person:
        return []
    shared = per_person[0]
    for other in per_person[1:]:
        shared = [
            (max(a0, b0), min(a1, b1))
            for a0, a1 in shared
            for b0, b1 in other
            if max(a0, b0) < min(a1, b1)
        ]
    return shared
