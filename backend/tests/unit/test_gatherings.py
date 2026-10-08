"""Recurrence -> occurrence generation (architecture rule 4). Pure; no database."""

import uuid
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.domain.enums import Recurrence, Weekday
from app.domain.gatherings import GatheringTypeSpec
from app.services.gatherings import occurrences

CHICAGO = "America/Chicago"
LOS_ANGELES = "America/Los_Angeles"


def weekly(weekday: Weekday, at: time, minutes: int = 75, active: bool = True) -> GatheringTypeSpec:
    return GatheringTypeSpec(uuid.uuid4(), Recurrence.WEEKLY, weekday, None, at, minutes, active)


def one_off(day: date, at: time, minutes: int = 90) -> GatheringTypeSpec:
    return GatheringTypeSpec(uuid.uuid4(), Recurrence.ONE_OFF, None, day, at, minutes)


def local(instant: datetime, zone: str = CHICAGO) -> time:
    return instant.astimezone(ZoneInfo(zone)).time()


def test_occurrences_are_utc_instants() -> None:
    (o,) = occurrences(
        [weekly(Weekday.SUNDAY, time(9, 30))], CHICAGO, date(2026, 10, 11), date(2026, 10, 11)
    )
    assert o.start_at.tzinfo is UTC and o.end_at.tzinfo is UTC


def test_weekly_gatherings_land_on_their_weekday_every_week() -> None:
    specs = [
        weekly(Weekday.SUNDAY, time(9, 30)),
        weekly(Weekday.WEDNESDAY, time(19, 0)),
        weekly(Weekday.FRIDAY, time(19, 0)),
    ]
    result = occurrences(specs, CHICAGO, date(2026, 10, 5), date(2026, 11, 1))  # Mon..Sun

    by_type = {s.id: [o for o in result if o.gathering_type_id == s.id] for s in specs}
    assert [len(v) for v in by_type.values()] == [4, 4, 4]
    for spec in specs:
        assert spec.weekday is not None
        for o in by_type[spec.id]:
            local = o.start_at.astimezone(ZoneInfo(CHICAGO))
            assert local.weekday() == spec.weekday.number
            assert local.time() == spec.local_start_time
    assert result == sorted(result, key=lambda o: o.start_at)


def test_window_is_inclusive_on_both_ends() -> None:
    spec = weekly(Weekday.SUNDAY, time(9, 30))
    result = occurrences([spec], CHICAGO, date(2026, 10, 11), date(2026, 10, 18))
    assert [o.start_at.astimezone(ZoneInfo(CHICAGO)).date() for o in result] == [
        date(2026, 10, 11),
        date(2026, 10, 18),
    ]


def test_local_time_is_kept_across_daylight_saving_change() -> None:
    # US DST ends 2026-11-01: Chicago goes from UTC-5 to UTC-6.
    spec = weekly(Weekday.SUNDAY, time(9, 30))
    before, after = occurrences([spec], CHICAGO, date(2026, 10, 25), date(2026, 11, 1))

    assert local(before.start_at) == local(after.start_at) == time(9, 30)
    assert before.start_at.astimezone(UTC) == datetime(2026, 10, 25, 14, 30, tzinfo=UTC)
    assert after.start_at.astimezone(UTC) == datetime(2026, 11, 1, 15, 30, tzinfo=UTC)


def test_duration_is_real_elapsed_time_across_the_dst_night() -> None:
    # 01:00 CDT + 2h of real time ends at 02:00 CST (clocks fall back at 02:00).
    spec = weekly(Weekday.SUNDAY, time(1, 0), minutes=120)
    (o,) = occurrences([spec], CHICAGO, date(2026, 11, 1), date(2026, 11, 1))
    assert o.end_at - o.start_at == timedelta(hours=2)
    assert o.end_at.astimezone(ZoneInfo(CHICAGO)).time() == time(2, 0)


def test_same_local_time_in_two_time_zones_is_two_different_instants() -> None:
    spec = weekly(Weekday.SUNDAY, time(11, 0))
    (chicago,) = occurrences([spec], CHICAGO, date(2026, 10, 11), date(2026, 10, 11))
    (la,) = occurrences([spec], LOS_ANGELES, date(2026, 10, 11), date(2026, 10, 11))
    assert chicago.start_at.astimezone(ZoneInfo(CHICAGO)).time() == time(11, 0)
    assert la.start_at.astimezone(ZoneInfo(LOS_ANGELES)).time() == time(11, 0)
    assert la.start_at - chicago.start_at == timedelta(hours=2)


def test_one_off_appears_once_and_only_inside_the_window() -> None:
    christmas = one_off(date(2026, 12, 24), time(17, 0))
    inside = occurrences([christmas], LOS_ANGELES, date(2026, 12, 1), date(2027, 1, 31))
    outside = occurrences([christmas], LOS_ANGELES, date(2026, 10, 1), date(2026, 12, 23))
    assert len(inside) == 1
    assert inside[0].start_at == datetime(2026, 12, 24, 17, 0, tzinfo=ZoneInfo(LOS_ANGELES))
    assert inside[0].end_at - inside[0].start_at == timedelta(minutes=90)
    assert outside == []


def test_inactive_types_generate_nothing() -> None:
    spec = weekly(Weekday.SUNDAY, time(9, 30), active=False)
    assert occurrences([spec], CHICAGO, date(2026, 10, 1), date(2026, 12, 31)) == []


def test_midweek_gatherings_overlap_in_real_time() -> None:
    """Prayer night 19:00-20:15 and youth 19:30-21:00 overlap, same as a Sunday clash would."""
    prayer = weekly(Weekday.WEDNESDAY, time(19, 0), minutes=75)
    youth = weekly(Weekday.WEDNESDAY, time(19, 30), minutes=90)
    a, b = occurrences([prayer, youth], CHICAGO, date(2026, 10, 14), date(2026, 10, 14))
    assert a.start_at < b.end_at and b.start_at < a.end_at
