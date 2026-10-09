"""Name matching and intake building: questions, never guesses (brief §11 intake rows)."""

import uuid
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import pytest

from app.domain.enums import QuestionKind, Weekday
from app.domain.intake import GatheringRef, IntakeContext, ParsedEntry, PersonRef, RoleRef
from app.services.intake import (
    LEAVE_OUT,
    IntakeAnswerError,
    apply_answer,
    assignments,
    build_intake,
    is_ready,
    render_intake,
    unknown_names,
)
from app.services.name_matching import Ambiguous, Matched, NotOnTeam, Unknown, match_name, normalize

K = QuestionKind
TZ = ZoneInfo("America/Chicago")


def person(name: str, *nicknames: str) -> PersonRef:
    return PersonRef(uuid.uuid4(), name, nicknames)


ANNA_PARKER = person("Anna Parker", "Anna P.")
ANNA_PETERSON = person("Anna Peterson", "Anna P.")
RACHEL = person("Rachel Turner")
EMILY = person("Emily Brooks")
SARAH = person("Sarah Collins")
DAVID = person("David Morales", "Dave")
MEGAN = person("Megan Lee")
TEAM = (ANNA_PARKER, ANNA_PETERSON, RACHEL, EMILY, SARAH)
OTHERS = (DAVID, MEGAN)

HELPER, LEAD, CHECKIN = (
    RoleRef(uuid.uuid4(), "Helper"),
    RoleRef(uuid.uuid4(), "Lead Teacher"),
    RoleRef(uuid.uuid4(), "Check-in"),
)


def gathering(name: str, day: date, at: time, serves: bool = True) -> GatheringRef:
    return GatheringRef(uuid.uuid4(), name, datetime.combine(day, at, tzinfo=TZ), serves)


SUN = date(2026, 10, 11)
G930 = gathering("Sunday 9:30 Service", SUN, time(9, 30))
G1100 = gathering("Sunday 11:00 Service", SUN, time(11, 0))
WED_PRAYER = gathering("Wednesday Prayer Night", date(2026, 10, 14), time(19, 0), serves=False)
WED_YOUTH = gathering("Wednesday Youth", date(2026, 10, 14), time(19, 30), serves=False)
G930_NEXT = gathering("Sunday 9:30 Service", date(2026, 10, 18), time(9, 30))


def ctx(**overrides: object) -> IntakeContext:
    base = IntakeContext(
        ministry_id=uuid.uuid4(),
        ministry_name="Kids",
        team=TEAM,
        others=OTHERS,
        roles=(LEAD, HELPER, CHECKIN),
        gatherings=(G930, G1100, WED_PRAYER, WED_YOUTH, G930_NEXT),
        today=date(2026, 10, 8),
        timezone="America/Chicago",
    )
    return IntakeContext(**{**base.__dict__, **overrides})  # type: ignore[arg-type]


def entry(
    names: list[str],
    *,
    day: str | None = "2026-10-11",
    at: str | None = "09:30",
    role: str = "Helper",
    both: bool = False,
    label: str | None = None,
    weekday: Weekday | None = None,
) -> ParsedEntry:
    return ParsedEntry(
        date=day,
        weekday=weekday,
        time=at,
        gathering=label,
        all_gatherings_that_day=both,
        role_as_written=role,
        role=None,
        names=names,
    )


# ---------------------------------------------------------------------------
# Name matching
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("written", "expected"),
    [("Rachel Turner", RACHEL), ("rachel", RACHEL), ("  EMILY  ", EMILY), ("Emily B.", EMILY)],
)
def test_exact_name_unique_first_name_and_initial_match(written: str, expected: PersonRef) -> None:
    assert match_name(written, TEAM, OTHERS) == Matched(expected)


def test_anna_p_matches_two_people_and_is_never_merged() -> None:
    for written in ("Anna P.", "anna p", "Anna"):
        result = match_name(written, TEAM, OTHERS)
        assert isinstance(result, Ambiguous), written
        assert set(result.candidates) == {ANNA_PARKER, ANNA_PETERSON}


def test_a_recorded_nickname_matches() -> None:
    assert match_name("Dave", (DAVID,), ()) == Matched(DAVID)


def test_someone_outside_the_team_is_flagged_not_assigned() -> None:
    assert match_name("Megan", TEAM, OTHERS) == NotOnTeam((MEGAN,))


def test_a_new_name_is_unknown_even_if_similar() -> None:
    assert match_name("Annie", TEAM, OTHERS) == Unknown()
    assert match_name("Rachael", TEAM, OTHERS) == Unknown()  # no fuzzy matching


def test_normalize() -> None:
    assert normalize("  Anna  P. ") == normalize("anna p") == "anna p"
    assert normalize("O'Brien-Smith") == "o'brien-smith"


# ---------------------------------------------------------------------------
# Building the intake
# ---------------------------------------------------------------------------


def test_clear_entries_resolve_without_questions() -> None:
    draft = build_intake([entry(["Rachel", "Emily B."])], ctx())
    assert draft.questions == []
    assert is_ready(draft)
    assert {(a.gathering_id, a.role_id, a.person_id) for a in assignments(draft)} == {
        (G930.id, HELPER.id, RACHEL.id),
        (G930.id, HELPER.id, EMILY.id),
    }


def test_ambiguous_name_gives_one_question_for_all_its_slots() -> None:
    draft = build_intake(
        [entry(["Anna P."]), entry(["Anna P."], at="11:00"), entry(["Rachel"])], ctx()
    )
    (question,) = draft.questions
    assert question.kind is K.AMBIGUOUS_NAME
    assert len(question.slot_ids) == 2
    assert {c.value for c in question.choices} == {ANNA_PARKER.id, ANNA_PETERSON.id, None}
    assert not is_ready(draft)


def test_unknown_name_offers_suggestions_first_then_team_then_leave_out() -> None:
    context = ctx(suggestions={"annie": (ANNA_PETERSON.id,)})
    draft = build_intake([entry(["Annie"])], context)
    (question,) = draft.questions
    assert question.kind is K.UNKNOWN_NAME
    assert "It might be Anna Peterson" in question.prompt
    assert "can't add new people" in question.prompt
    assert question.choices[0].value == ANNA_PETERSON.id and question.choices[0].learn_nickname
    assert question.choices[-1].id == LEAVE_OUT
    assert unknown_names([entry(["Annie", "Rachel", "Anna P.", "Megan"])], context) == ["Annie"]


def test_two_services_and_no_time_asks_which_gathering() -> None:
    draft = build_intake([entry(["Rachel"], at=None)], ctx())
    (question,) = draft.questions
    assert question.kind is K.WHICH_GATHERING
    assert [c.value for c in question.choices] == [G930.id, G1100.id, None]


def test_both_services_expands_to_every_service_that_day() -> None:
    draft = build_intake([entry(["Rachel"], at=None, both=True)], ctx())
    assert draft.questions == []
    assert {a.gathering_id for a in assignments(draft)} == {G930.id, G1100.id}


def test_a_date_with_one_relevant_gathering_needs_no_time() -> None:
    draft = build_intake([entry(["Rachel"], day="2026-10-18", at=None)], ctx())
    assert draft.questions == []
    assert assignments(draft)[0].gathering_id == G930_NEXT.id


def test_label_picks_the_gathering() -> None:
    draft = build_intake([entry(["Rachel"], at=None, label="11:00 service")], ctx())
    assert assignments(draft)[0].gathering_id == G1100.id


def test_role_shorthand_and_plurals_resolve_or_ask() -> None:
    plural = build_intake([entry(["Rachel"], role="helpers")], ctx())
    assert plural.questions == [] and assignments(plural)[0].role_id == HELPER.id
    shorthand = build_intake([entry(["Rachel"], role="chk")], ctx())
    (question,) = shorthand.questions
    assert question.kind is K.UNKNOWN_ROLE


# ---------------------------------------------------------------------------
# Answers
# ---------------------------------------------------------------------------


def test_answering_resolves_slots_and_learns_nicknames() -> None:
    draft = build_intake(
        [entry(["Anna P.", "Annie"])], ctx(suggestions={"annie": (ANNA_PETERSON.id,)})
    )
    ambiguous, unknown = draft.questions

    draft = apply_answer(
        draft, ambiguous.id, next(c.id for c in ambiguous.choices if c.value == ANNA_PARKER.id)
    )
    draft = apply_answer(draft, unknown.id, unknown.choices[0].id)

    assert is_ready(draft)
    assert {a.person_id for a in assignments(draft)} == {ANNA_PARKER.id, ANNA_PETERSON.id}
    assert [(n.person_id, n.nickname) for n in draft.nicknames] == [(ANNA_PETERSON.id, "Annie")]
    assert "Anna Parker" in render_intake(draft)


def test_leaving_out_drops_the_slot_and_its_other_questions() -> None:
    draft = build_intake([entry(["Jessie"], at=None, role="kb")], ctx())
    assert {q.kind for q in draft.questions} == {K.WHICH_GATHERING, K.UNKNOWN_ROLE, K.UNKNOWN_NAME}
    name_q = next(q for q in draft.questions if q.kind is K.UNKNOWN_NAME)
    draft = apply_answer(draft, name_q.id, LEAVE_OUT)
    assert draft.questions == []  # nothing left to ask about a slot that's left out
    assert is_ready(draft) and assignments(draft) == []
    assert "left out" in render_intake(draft)


def test_wrong_answers_are_refused() -> None:
    draft = build_intake([entry(["Anna P."])], ctx())
    with pytest.raises(IntakeAnswerError):
        apply_answer(draft, "q99", "c1")
    with pytest.raises(IntakeAnswerError):
        apply_answer(draft, draft.questions[0].id, "c99")
