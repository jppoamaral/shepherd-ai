"""Model behaviour for onboarding, against the real Azure OpenAI deployment.

Run with:  uv run pytest -m eval tests/evals
Skipped when AZURE_OPENAI_* is not configured; excluded from the default run.

Each case puts the agent at a topic with a realistic draft, sends a messy admin
message, and checks the structured result that code would then act on.
"""

import json
from collections.abc import Iterator
from datetime import date, time

import pytest
from sqlalchemy.orm import Session

from app.agents.onboarding import OnboardingAgent
from app.config import get_settings
from app.db.repositories.onboarding import OnboardingRepository, OnboardingState
from app.domain.enums import GatheringKind, OnboardingTopic, Period, Recurrence, Weekday
from app.domain.profile import ChurchProfileDraft
from app.llm.factory import get_llm, is_configured
from app.services.onboarding import Started, start_onboarding
from tests.profile_script import SCRIPT, run

pytestmark = [
    pytest.mark.eval,
    pytest.mark.skipif(not is_configured(get_settings()), reason="Azure OpenAI not configured"),
]
T = OnboardingTopic


@pytest.fixture
def started(session: Session) -> Started:
    return start_onboarding(session, "Eval Chapel", "Pat Admin")


@pytest.fixture
def agent(session: Session, started: Started) -> Iterator[OnboardingAgent]:
    yield OnboardingAgent(session, started.church.id, get_llm())


def at(
    session: Session, started: Started, topic: OnboardingTopic, draft: ChurchProfileDraft
) -> None:
    repo = OnboardingRepository(session, started.church.id)
    state = repo.get(started.session.id)
    assert state is not None
    repo.save(OnboardingState(**{**state.__dict__, "topic": topic, "draft": draft}))


def draft_after(session: Session, started: Started) -> ChurchProfileDraft:
    state = OnboardingRepository(session, started.church.id).get(started.session.id)
    assert state is not None
    return state.draft


def prior(topic: OnboardingTopic) -> ChurchProfileDraft:
    """A draft with every section before `topic` answered by the scripted admin."""
    steps = [step for step in SCRIPT if list(T).index(step[0]) < list(T).index(topic)]
    return run(steps)


def test_city_becomes_an_iana_time_zone(
    session: Session, started: Started, agent: OnboardingAgent
) -> None:
    agent.handle_message(
        started.session.id, "We're a small church in Dallas, Texas. Messages in English please."
    )
    draft = draft_after(session, started)
    assert draft.timezone == "America/Chicago"
    assert draft.language == "en"


def test_messy_gatherings_with_a_weekday_night_and_a_special_event(
    session: Session, started: Started, agent: OnboardingAgent
) -> None:
    at(session, started, T.GATHERINGS, prior(T.GATHERINGS))
    agent.handle_message(
        started.session.id,
        "sunday service 10:30am, runs about an hour and a half. wednesday nights we do prayer at 7, "
        "an hour. and christmas eve candlelight at 5pm this year, 90 mins, that's a big special one",
    )
    gatherings = {g.weekday or g.one_off_date: g for g in draft_after(session, started).gatherings}
    assert gatherings[Weekday.SUNDAY].local_start_time == time(10, 30)
    assert gatherings[Weekday.SUNDAY].duration_minutes == 90
    wednesday = gatherings[Weekday.WEDNESDAY]
    assert (wednesday.local_start_time, wednesday.duration_minutes) == (time(19, 0), 60)
    christmas = gatherings[date(2026, 12, 24)]
    assert christmas.recurrence is Recurrence.ONE_OFF and christmas.kind is GatheringKind.SPECIAL
    assert christmas.local_start_time == time(17, 0)


def test_a_vague_time_gets_a_question_not_a_guess(
    session: Session, started: Started, agent: OnboardingAgent
) -> None:
    at(session, started, T.GATHERINGS, prior(T.GATHERINGS))
    reply = agent.handle_message(started.session.id, "We meet Sunday mornings.")
    assert draft_after(session, started).gatherings == []
    assert "?" in reply.message


def test_saying_thats_all_confirms_the_section(
    session: Session, started: Started, agent: OnboardingAgent
) -> None:
    draft = run(SCRIPT[:2])
    draft.confirmed.remove(T.GATHERINGS)
    at(session, started, T.GATHERINGS, draft)
    reply = agent.handle_message(started.session.id, "yep that's everything")
    assert T.GATHERINGS in draft_after(session, started).confirmed
    assert reply.topic is T.MINISTRIES


def test_ministry_nicknames_become_aliases(
    session: Session, started: Started, agent: OnboardingAgent
) -> None:
    at(session, started, T.MINISTRIES, prior(T.MINISTRIES))
    agent.handle_message(
        started.session.id,
        "Worship team (everyone just calls it the band), Kids Church, and the tech crew for sound and slides",
    )
    ministries = {m.name.casefold(): m for m in draft_after(session, started).ministries}
    assert len(ministries) == 3
    worship = next(m for name, m in ministries.items() if "worship" in name)
    assert any("band" in a.casefold() for a in worship.aliases)


def test_who_schedules_and_who_approves(
    session: Session, started: Started, agent: OnboardingAgent
) -> None:
    at(session, started, T.LEADERS, prior(T.LEADERS))
    agent.handle_message(
        started.session.id,
        "David Morales does the worship schedule and signs off on it himself. For kids, Sarah Collins "
        "makes the schedule and Pastor Mike Harris approves it.",
    )
    ministries = {m.name: m for m in draft_after(session, started).ministries}
    (david,) = ministries["Worship"].leaders
    assert (david.can_schedule, david.can_approve) == (True, True)
    kids = {leader.name: leader for leader in ministries["Kids"].leaders}
    sarah = next(v for k, v in kids.items() if "Sarah" in k)
    mike = next(v for k, v in kids.items() if "Mike" in k)
    assert (sarah.can_schedule, sarah.can_approve) == (True, False)
    assert (mike.can_schedule, mike.can_approve) == (False, True)


def test_serving_frequency_in_plain_words(
    session: Session, started: Started, agent: OnboardingAgent
) -> None:
    at(session, started, T.LOAD_RULES, prior(T.LOAD_RULES))
    agent.handle_message(
        started.session.id,
        "Twice a month is plenty for anyone, flag it if it's more than that. And let me know if "
        "someone hasn't served in 6 weeks.",
    )
    draft = draft_after(session, started)
    assert [(r.period, r.normal_max, r.warning_above) for r in draft.load_rules] == [
        (Period.MONTH, 2, 2)
    ]
    assert draft.absence_threshold_weeks == 6


def test_personal_details_never_reach_the_draft(
    session: Session, started: Started, agent: OnboardingAgent
) -> None:
    agent.handle_message(
        started.session.id,
        "We're in Chicago. Sorry for the delay, our pastor is going through a divorce and his "
        "mom is in the hospital.",
    )
    stored = json.dumps(draft_after(session, started).model_dump(mode="json")).casefold()
    assert "divorce" not in stored and "hospital" not in stored


MESSY_SAMPLE = """\
SEPTEMBER SERVING — GRACE
Sun 9/6 9:30am
  Worship: Keys - Anna P. | Vocals - Hannah, Megan
  Kids: Helpers - Rachel, Emily
Wed 9/9 7pm prayer night
  Worship: Keys - Anna P.
Sun 9/13 9:30am
  Worship: Keys - Dave | Vocals - Hannah, Megan
  Kids: Helpers - Emily, Anna Peterson
Wed 9/16 7pm prayer night
  Worship: Keys - Anna P.
Sun 9/20 9:30
  Worship: Keys - Anna P. | Vocals - Hannah, Megan, Rachel
  Kids: Helpers - Rachel, Emily
"""


def test_a_messy_sample_schedule_becomes_suggestions(
    session: Session, started: Started, agent: OnboardingAgent
) -> None:
    at(session, started, T.GATHERINGS, prior(T.GATHERINGS))
    agent.handle_sample(started.session.id, MESSY_SAMPLE)
    draft = draft_after(session, started)

    weekly = {
        (g.weekday, g.local_start_time)
        for g in draft.gatherings
        if g.recurrence is Recurrence.WEEKLY
    }
    assert (Weekday.SUNDAY, time(9, 30)) in weekly
    assert (Weekday.WEDNESDAY, time(19, 0)) in weekly
    assert all(g.inferred for g in draft.gatherings)

    vocals = next(
        r for m in draft.ministries for r in m.roles if r.name.casefold().startswith("vocal")
    )
    assert [m.minimum for m in vocals.minimums] == [2]  # 2, 2, 3 seen -> most common is 2

    stored = json.dumps(draft.model_dump(mode="json"))
    assert "Hannah" not in stored and "Rachel" not in stored  # counts only, never names
