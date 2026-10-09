"""Shared slots for a conflict huddle (brief §11 huddle rows)."""

import uuid
from datetime import datetime, time
from zoneinfo import ZoneInfo

from app.domain.enums import Weekday
from app.services.huddle_slots import Window, common_slots, nearest_options

TZ = ZoneInfo("America/Chicago")
SARAH, DAVID = uuid.uuid4(), uuid.uuid4()
NAMES = {SARAH: "Sarah Collins", DAVID: "David Morales"}
THU_EVENING = datetime(2026, 10, 8, 18, 0, tzinfo=TZ)
SUNDAY_930 = datetime(2026, 10, 11, 9, 30, tzinfo=TZ)


def test_overlapping_windows_give_three_spread_slots_before_the_gathering() -> None:
    windows = {
        SARAH: [Window(Weekday.SATURDAY, time(9, 30), time(11, 30))],
        DAVID: [Window(Weekday.SATURDAY, time(10, 0), time(12, 0))],
    }
    slots = common_slots(windows, THU_EVENING, SUNDAY_930)
    assert [s.label for s in slots] == [
        "Sat 10 Oct, 10:00 AM to 10:15 AM",
        "Sat 10 Oct, 10:30 AM to 10:45 AM",
        "Sat 10 Oct, 11:00 AM to 11:15 AM",
    ]


def test_past_and_after_gathering_times_are_never_offered() -> None:
    windows = {
        SARAH: [
            Window(Weekday.THURSDAY, time(12, 0), time(13, 0)),
            Window(Weekday.SUNDAY, time(9, 0), time(12, 0)),
        ],
        DAVID: [
            Window(Weekday.THURSDAY, time(12, 0), time(13, 0)),
            Window(Weekday.SUNDAY, time(9, 0), time(12, 0)),
        ],
    }
    slots = common_slots(windows, THU_EVENING, SUNDAY_930)
    # Thursday noon already passed; Sunday 9:00 fits before 9:30, 9:30 doesn't.
    assert [s.label for s in slots] == ["Sun 11 Oct, 9:00 AM to 9:15 AM"]


def test_no_common_window_lists_the_nearest_options() -> None:
    windows = {
        SARAH: [Window(Weekday.MONDAY, time(9, 0), time(11, 0))],
        DAVID: [Window(Weekday.TUESDAY, time(18, 0), time(20, 0))],
    }
    assert common_slots(windows, THU_EVENING, SUNDAY_930) == []
    labels = [o.label for o in nearest_options(windows, NAMES, THU_EVENING, SUNDAY_930)]
    assert labels[0] == "Sarah Collins is free Mon 12 Oct, 9:00 AM to 11:00 AM"
    assert "David Morales is free Tue 13 Oct, 6:00 PM to 8:00 PM" in labels


def test_a_leader_without_windows_is_named() -> None:
    labels = [
        o.label for o in nearest_options({SARAH: [], DAVID: []}, NAMES, THU_EVENING, SUNDAY_930)
    ]
    assert labels == [
        "Sarah Collins has no availability windows set",
        "David Morales has no availability windows set",
    ]
