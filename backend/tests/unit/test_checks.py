"""Deterministic checks (brief §5 and §11 'Checks' rows). Pure; no database."""

import uuid
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from app.domain.checks import AssignmentFact, LoadRuleFact, MemberFact, PreferenceFact, RoleNeed
from app.domain.enums import FindingType, Period
from app.services.checks import (
    NOTED,
    WARNING,
    absent,
    below_minimum,
    blockouts,
    load,
    overlaps,
)

TZ = ZoneInfo("America/Chicago")
ANNA, HANNAH = uuid.uuid4(), uuid.uuid4()
KIDS, WORSHIP, MEDIA = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
NAMES = {
    ANNA: "Anna Parker",
    HANNAH: "Hannah Wright",
    KIDS: "Kids",
    WORSHIP: "Worship",
    MEDIA: "Media",
}


def fact(
    person: uuid.UUID,
    ministry: uuid.UUID,
    role: str,
    gathering: str,
    local: datetime,
    minutes: int,
    gathering_id: uuid.UUID | None = None,
) -> AssignmentFact:
    start = local.astimezone(UTC)
    end = start + timedelta(minutes=minutes)
    return AssignmentFact(
        id=uuid.uuid4(),
        person_id=person,
        person_name=NAMES[person],
        ministry_id=ministry,
        ministry_name=NAMES[ministry],
        role_id=uuid.uuid4(),
        role_name=role,
        gathering_id=gathering_id or uuid.uuid4(),
        gathering_name=gathering,
        start=start,
        end=end,
        local_start=local,
        local_end=end.astimezone(TZ),
    )


SUN_930 = datetime(2026, 10, 11, 9, 30, tzinfo=TZ)
SUN_1100 = datetime(2026, 10, 11, 11, 0, tzinfo=TZ)
WED_1900 = datetime(2026, 10, 14, 19, 0, tzinfo=TZ)
WED_1930 = datetime(2026, 10, 14, 19, 30, tzinfo=TZ)
G930 = uuid.uuid4()


def test_same_service_in_two_ministries_is_a_double_booking() -> None:
    (issue,) = overlaps(
        [
            fact(ANNA, KIDS, "Helper", "Sunday 9:30 Service", SUN_930, 75, G930),
            fact(ANNA, WORSHIP, "Keys", "Sunday 9:30 Service", SUN_930, 75, G930),
        ]
    )
    assert issue.type is FindingType.OVERLAP and issue.severity == WARNING
    assert set(issue.ministry_ids) == {KIDS, WORSHIP}
    assert issue.text == (
        "Anna Parker is booked twice at Sunday 9:30 Service (Sun 11 Oct 9:30 AM): Kids (Helper) and Worship (Keys)."
    )


def test_wednesday_prayer_vs_youth_is_flagged_like_a_sunday_conflict() -> None:
    (issue,) = overlaps(
        [
            fact(HANNAH, WORSHIP, "Vocals", "Wednesday Prayer Night", WED_1900, 75),
            fact(HANNAH, MEDIA, "Sound", "Wednesday Youth", WED_1930, 90),
        ]
    )
    assert issue.type is FindingType.OVERLAP
    assert "Wednesday Prayer Night 7:00 PM to 8:15 PM (Worship, Vocals)" in issue.text
    assert "Wednesday Youth 7:30 PM to 9:00 PM (Media, Sound)" in issue.text


def test_back_to_back_services_are_not_an_overlap() -> None:
    assert (
        overlaps(
            [
                fact(ANNA, WORSHIP, "Keys", "Sunday 9:30 Service", SUN_930, 75),
                fact(ANNA, WORSHIP, "Keys", "Sunday 11:00 Service", SUN_1100, 75),
                fact(ANNA, WORSHIP, "Keys", "Sunday 9:30 Service", SUN_930 + timedelta(days=7), 90),
                fact(
                    ANNA, WORSHIP, "Keys", "Sunday 11:00 Service", SUN_1100 + timedelta(days=7), 75
                ),  # touches, no overlap
            ]
        )
        == []
    )


ANNA_WEEK = [
    fact(ANNA, KIDS, "Helper", "Sunday 9:30 Service", SUN_930, 75),
    fact(ANNA, WORSHIP, "Keys", "Sunday 9:30 Service", SUN_930, 75),
    fact(ANNA, WORSHIP, "Keys", "Sunday 11:00 Service", SUN_1100, 75),
    fact(ANNA, WORSHIP, "Keys", "Wednesday Prayer Night", WED_1900, 75),
]


def test_overloaded_person_is_warned_above_preference_and_church_limit() -> None:
    (issue,) = load(
        ANNA_WEEK,
        [LoadRuleFact(Period.WEEK, 1, 2)],
        {ANNA: PreferenceFact(2, Period.WEEK)},
        "Grace",
    )
    assert issue.type is FindingType.LOAD and issue.severity == WARNING
    assert issue.text == (
        "Anna Parker is serving 4 times the week of 11 Oct, above their preferred 2 "
        "and above Grace's limit (more than 2 is a warning)."
    )
    assert set(issue.ministry_ids) == {KIDS, WORSHIP}
    assert issue.details["count"] == 4


def test_sunday_and_the_following_wednesday_are_the_same_church_week() -> None:
    (issue,) = load(ANNA_WEEK, [LoadRuleFact(Period.WEEK, 3, 3)], {}, "Grace")
    assert issue.details["period_start"] == "2026-10-11"


def test_above_normal_but_within_limit_is_only_noted() -> None:
    two = ANNA_WEEK[1:3]
    (issue,) = load(two, [LoadRuleFact(Period.WEEK, 1, 2)], {}, "Grace")
    assert issue.severity == NOTED and "above Grace's usual 1" in issue.text
    assert load(two, [LoadRuleFact(Period.WEEK, 2, 3)], {}, "Grace") == []


def test_a_monthly_cap_counts_per_month() -> None:
    sundays = [
        fact(ANNA, WORSHIP, "Keys", "Sunday 9:30 Service", SUN_930 + timedelta(weeks=w), 75)
        for w in range(4)
    ]
    (october,) = load(
        sundays[:3], [LoadRuleFact(Period.MONTH, 2, 2)], {}, "Riverside"
    )  # 11, 18, 25 Oct
    assert october.severity == WARNING and "in October" in october.text
    november_split = load(
        sundays[2:], [LoadRuleFact(Period.MONTH, 2, 2)], {}, "Riverside"
    )  # 25 Oct, 1 Nov
    assert november_split == []


def test_role_below_minimum() -> None:
    need = RoleNeed(
        WORSHIP,
        "Worship",
        uuid.uuid4(),
        "Vocals",
        uuid.uuid4(),
        "Sunday 9:30 Service",
        SUN_930,
        2,
        1,
    )
    (issue,) = below_minimum([need, RoleNeed(**{**need.__dict__, "filled": 2})])
    assert (
        issue.text
        == "Worship needs 2 Vocals at Sunday 9:30 Service (Sun 11 Oct 9:30 AM) and has 1."
    )


def test_blockout_flags_an_assignment_on_a_date_the_person_is_away() -> None:
    sunday = fact(
        ANNA, KIDS, "Helper", "Sunday 9:30 Service", datetime(2026, 10, 11, 9, 30, tzinfo=TZ), 75
    )
    away = {ANNA: [(date(2026, 10, 10), date(2026, 10, 11))]}  # inclusive
    (issue,) = blockouts([sunday], away)
    assert issue.type is FindingType.BLOCKOUT and issue.severity == WARNING
    assert issue.text == (
        "Anna Parker can't serve on Sun 11 Oct but is on the Kids roster (Helper) "
        "at Sunday 9:30 Service 9:30 AM."
    )
    assert issue.person_ids == (ANNA,) and issue.ministry_ids == (KIDS,)
    assert issue.on == "2026-10-11"


def test_blockout_ignores_other_days_other_people_and_uses_the_church_local_day() -> None:
    sunday = fact(
        ANNA, KIDS, "Helper", "Sunday 9:30 Service", datetime(2026, 10, 11, 9, 30, tzinfo=TZ), 75
    )
    assert blockouts([sunday], {ANNA: [(date(2026, 10, 12), date(2026, 10, 18))]}) == []
    assert blockouts([sunday], {HANNAH: [(date(2026, 10, 11), date(2026, 10, 11))]}) == []
    # 9 PM Wednesday in Chicago is already Thursday in UTC; the blockout is for the local day.
    late = fact(
        HANNAH, MEDIA, "Sound", "Wednesday Youth", datetime(2026, 10, 14, 21, 0, tzinfo=TZ), 60
    )
    assert blockouts([late], {HANNAH: [(date(2026, 10, 15), date(2026, 10, 15))]}) == []
    assert len(blockouts([late], {HANNAH: [(date(2026, 10, 14), date(2026, 10, 14))]})) == 1


TODAY = date(2026, 10, 11)


def member(
    last_served: date | None, *, asked_on: date | None = None, upcoming: bool = False
) -> MemberFact:
    return MemberFact(
        membership_id=uuid.uuid4(),
        person_id=HANNAH,
        person_name=NAMES[HANNAH],
        ministry_id=KIDS,
        ministry_name=NAMES[KIDS],
        last_served=last_served,
        asked_on=asked_on,
        upcoming=upcoming,
    )


def test_absent_from_the_threshold_week_on() -> None:
    six_weeks = TODAY - timedelta(weeks=6)
    assert absent([member(six_weeks + timedelta(days=1))], TODAY, 6) == []
    (issue,) = absent([member(six_weeks)], TODAY, 6)
    assert issue.type is FindingType.ABSENT and issue.severity == NOTED
    assert issue.text == "Hannah Wright hasn't served with Kids since 30 Aug."
    assert issue.details["weeks"] == 6 and issue.details["last_served"] == "2026-08-30"
    assert issue.person_ids == (HANNAH,) and issue.ministry_ids == (KIDS,)


def test_absent_skips_no_history_coming_rosters_and_a_recent_ask_me_later() -> None:
    long_ago = TODAY - timedelta(weeks=10)
    assert absent([member(None)], TODAY, 6) == []  # nothing on record to compare
    assert absent([member(long_ago, upcoming=True)], TODAY, 6) == []
    asked = TODAY - timedelta(weeks=4)
    assert absent([member(long_ago, asked_on=asked + timedelta(days=1))], TODAY, 6) == []
    assert len(absent([member(long_ago, asked_on=asked)], TODAY, 6)) == 1  # asked again
