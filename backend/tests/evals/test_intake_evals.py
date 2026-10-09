"""Schedule intake against the real model (run with `uv run pytest -m eval tests/evals`).

A messy Grace Kids schedule goes through the real steward agent; we check what
code ends up with: questions instead of guesses, and nothing personal kept.
"""

import json
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.steward import IntakeView, StewardAgent
from app.config import get_settings
from app.db.models import Ministry, Person, ScheduleIntake
from app.domain.enums import QuestionKind
from app.llm.factory import get_llm, is_configured
from tests.conftest import SEED_TODAY

pytestmark = [
    pytest.mark.eval,
    pytest.mark.skipif(not is_configured(get_settings()), reason="Azure OpenAI not configured"),
]
K = QuestionKind

MESSY_KIDS = """\
KIDS MIN — OCTOBER 🎈
Sun 10/11 (9:30 svc)
  Lead: Sarah
  helpers - Rachel, Anna P.
  chk-in: Megan
Sun 10/11 11am
  lead: Emily
  helpers: Annie + Anna Peterson
10/18 both services
  Lead teacher — Sarah
Oct 25th - 9:30
  Helpers: Rachel, Emily (Emily might be late, her mom is in the hospital)
"""


@pytest.fixture
def intake(session: Session, grace_id: uuid.UUID) -> IntakeView:
    kids = session.scalar(
        select(Ministry.id).where(Ministry.church_id == grace_id, Ministry.name == "Kids")
    )
    sarah = session.scalar(
        select(Person.id).where(Person.church_id == grace_id, Person.name == "Sarah Collins")
    )
    assert kids and sarah
    return StewardAgent(session, grace_id, get_llm(), today=SEED_TODAY).intake_schedule(
        kids, sarah, MESSY_KIDS
    )


def lines(view: IntakeView) -> list[str]:
    return view.summary.splitlines()


def test_anna_p_becomes_a_question_with_both_annas(intake: IntakeView) -> None:
    (question,) = [q for q in intake.questions if q.kind is K.AMBIGUOUS_NAME]
    assert question.subject == "Anna P."
    assert {c.label for c in question.choices} >= {"Anna Parker", "Anna Peterson"}


def test_annie_is_asked_about_never_matched(intake: IntakeView) -> None:
    (question,) = [q for q in intake.questions if q.subject == "Annie"]
    assert question.kind is K.UNKNOWN_NAME
    assert "It might be" in question.prompt and "Anna" in question.prompt
    assert not any(
        "Annie" in line and "(who?)" not in line and "Anna" in line for line in lines(intake)
    )


def test_dates_times_both_services_and_shorthand_resolve(intake: IntakeView) -> None:
    summary = intake.summary
    assert "Sunday 9:30 Service, Sun 11 Oct 9:30 AM · Lead Teacher · Sarah Collins" in summary
    assert "Sunday 11:00 Service, Sun 11 Oct 11:00 AM · Lead Teacher · Emily Brooks" in summary
    assert "Sunday 9:30 Service, Sun 11 Oct 9:30 AM · Check-in · Megan Lee" in summary
    # "both services" on 10/18 -> Sarah at both.
    assert "Sunday 9:30 Service, Sun 18 Oct 9:30 AM · Lead Teacher · Sarah Collins" in summary
    assert "Sunday 11:00 Service, Sun 18 Oct 11:00 AM · Lead Teacher · Sarah Collins" in summary
    assert "Sunday 9:30 Service, Sun 25 Oct 9:30 AM · Helper · Rachel Turner" in summary
    # Only the two name questions remain; dates, times and roles were all clear.
    assert {q.subject for q in intake.questions} == {"Anna P.", "Annie"}


def test_personal_notes_are_not_kept(session: Session, intake: IntakeView) -> None:
    stored = json.dumps(session.get_one(ScheduleIntake, intake.id).draft).casefold()
    assert "hospital" not in stored and "mom" not in stored and "late" not in stored
