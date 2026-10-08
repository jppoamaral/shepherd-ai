"""Recurrence -> concrete Gathering rows, in the church's time zone (architecture rule 4).

A weekly gathering keeps its local wall-clock time across daylight-saving changes
("Sunday 9:30" stays 9:30 local), so its UTC instant shifts. Durations are real
elapsed time, so an end time is always `start + duration`.

Occurrences are returned in UTC on purpose: Python compares and subtracts two
datetimes that share a tzinfo by wall clock, ignoring DST offsets, which would
make overlap and duration math wrong on transition nights. Convert to the
church's zone only for display.
"""

import uuid
from collections.abc import Iterable
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.db.models import Church, Gathering, GatheringType
from app.domain.enums import ProfileStatus, Recurrence
from app.domain.gatherings import GatheringTypeSpec, Occurrence


def occurrences(
    specs: Iterable[GatheringTypeSpec], timezone: str, start: date, end: date
) -> list[Occurrence]:
    """Every occurrence whose local date falls in `[start, end]`, sorted by start."""
    tz = ZoneInfo(timezone)
    result: list[Occurrence] = []
    for spec in specs:
        if not spec.active:
            continue
        for day in _local_dates(spec, start, end):
            start_at = datetime.combine(day, spec.local_start_time, tzinfo=tz).astimezone(UTC)
            end_at = start_at + timedelta(minutes=spec.duration_minutes)
            result.append(Occurrence(spec.id, start_at, end_at))
    return sorted(result, key=lambda o: (o.start_at, str(o.gathering_type_id)))


def _local_dates(spec: GatheringTypeSpec, start: date, end: date) -> list[date]:
    if spec.recurrence is Recurrence.ONE_OFF:
        assert spec.one_off_date is not None
        return [spec.one_off_date] if start <= spec.one_off_date <= end else []
    assert spec.weekday is not None
    first = start + timedelta(days=(spec.weekday.number - start.weekday()) % 7)
    weeks = (end - first).days // 7 + 1 if first <= end else 0
    return [first + timedelta(weeks=n) for n in range(weeks)]


def spec_from_model(gathering_type: GatheringType) -> GatheringTypeSpec:
    return GatheringTypeSpec(
        id=gathering_type.id,
        recurrence=gathering_type.recurrence,
        weekday=gathering_type.weekday,
        one_off_date=gathering_type.one_off_date,
        local_start_time=gathering_type.local_start_time,
        duration_minutes=gathering_type.duration_minutes,
        active=gathering_type.active,
    )


def ensure_gatherings(session: Session, church_id: uuid.UUID, start: date, end: date) -> int:
    """Create any missing Gathering rows for one church in `[start, end]`. Idempotent.

    Draft churches (profile not yet approved) get none.

    Returns the number of rows inserted. Does not commit.
    """
    church = session.get_one(Church, church_id)
    if church.profile_status is not ProfileStatus.APPROVED:
        return 0  # nothing runs until a person approves the profile
    types = session.scalars(select(GatheringType).where(GatheringType.church_id == church_id))
    rows = [
        {
            "id": uuid.uuid4(),
            "church_id": church_id,
            "gathering_type_id": o.gathering_type_id,
            "start_at": o.start_at,
            "end_at": o.end_at,
        }
        for o in occurrences((spec_from_model(t) for t in types), church.timezone, start, end)
    ]
    if not rows:
        return 0
    stmt = (
        insert(Gathering)
        .values(rows)
        .on_conflict_do_nothing(index_elements=["gathering_type_id", "start_at"])
        .returning(Gathering.id)
    )
    return len(session.execute(stmt).all())
