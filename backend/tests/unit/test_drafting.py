"""One simple roster suggestion: hard rules always hold, preferences are weighed."""

import uuid
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from app.domain.enums import Experience, Period
from app.services.drafting import Candidate, DraftFacts, Position, draft

TZ = ZoneInfo("America/Chicago")
HELPER = uuid.uuid4()
SUN_TYPE, WED_TYPE = uuid.uuid4(), uuid.uuid4()


def position(
    day: int,
    hour: int = 9,
    minute: int = 30,
    gtype: uuid.UUID = SUN_TYPE,
    name: str = "Sunday 9:30 Service",
) -> Position:
    local = datetime(2026, 10, day, hour, minute, tzinfo=TZ)
    start = local.astimezone(UTC)
    return Position(
        uuid.uuid4(), gtype, name, start, start + timedelta(minutes=75), local, HELPER, "Helper"
    )


def person(name: str, exp: Experience = Experience.EXPERIENCED) -> Candidate:
    return Candidate(uuid.uuid4(), name, {HELPER: exp})


def facts(candidates: list[Candidate], **kw: object) -> DraftFacts:
    base: dict[str, object] = dict(
        candidates=candidates,
        busy={},
        blockouts={},
        served={},
        period=Period.MONTH,
        usual=None,
        preferred={},
        preferred_gatherings={},
    )
    base.update(kw)
    return DraftFacts(**base)  # type: ignore[arg-type]


RACHEL, EMILY, MEGAN = (
    person("Rachel Turner", Experience.NEW),
    person("Emily Brooks", Experience.VETERAN),
    person("Megan Lee"),
)


def test_blockouts_and_overlaps_are_never_drafted() -> None:
    sunday = position(11)
    busy = {
        EMILY.person_id: [
            (sunday.start - timedelta(minutes=30), sunday.start + timedelta(minutes=30))
        ]
    }
    blocked = {RACHEL.person_id: [(date(2026, 10, 11), date(2026, 10, 11))]}
    (line,) = draft([sunday], facts([RACHEL, EMILY, MEGAN], busy=busy, blockouts=blocked))
    assert line.name == "Megan Lee"
    assert {a.name for a in line.alternatives} == set()


def test_only_people_with_the_role_and_no_one_free_leaves_it_open() -> None:
    other_role = Candidate(uuid.uuid4(), "Tom Becker", {uuid.uuid4(): Experience.VETERAN})
    (line,) = draft([position(11)], facts([other_role]))
    assert line.person_id is None
    assert line.reason == "Oct 11 Helper: no one free on your team."


def test_rotation_spreads_serving_around() -> None:
    lines = draft([position(4), position(11), position(18)], facts([RACHEL, EMILY, MEGAN]))
    assert len({line.person_id for line in lines}) == 3
    assert lines[0].reason.endswith("hasn't served yet this month.")


def test_preferred_gathering_wins_and_is_named() -> None:
    lines = draft(
        [position(11)], facts([RACHEL, EMILY], preferred_gatherings={RACHEL.person_id: {SUN_TYPE}})
    )
    assert lines[0].name == "Rachel Turner"
    assert lines[0].reason == "Rachel prefers the Sunday 9:30 Service, and is free then."


def test_a_small_team_still_fills_the_slot_and_marks_it() -> None:
    lines = draft(
        [position(4), position(11), position(18)],
        facts([EMILY], preferred={EMILY.person_id: (2, Period.MONTH)}),
    )
    assert [line.name for line in lines] == ["Emily Brooks"] * 3
    assert lines[2].flags == ["Above preference: Emily, 3 times this month (prefers 2)"]
    assert lines[1].flags == []


def test_existing_assignments_count_toward_the_period() -> None:
    oct_bucket = date(2026, 10, 1)
    (line,) = draft(
        [position(11)], facts([RACHEL, EMILY], served={(RACHEL.person_id, oct_bucket): 2})
    )
    assert line.name == "Emily Brooks"
