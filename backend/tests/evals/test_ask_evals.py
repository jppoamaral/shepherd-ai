"""Ask Shepherd's question parsing against the real model (`uv run pytest -m eval tests/evals`).

The model only says what was asked; these check the intent, the name as written and
the resolved date for the questions a leader is likely to type in the demo.
"""

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import Ministry, Person
from app.domain.ask import ParsedQuestion
from app.domain.enums import AskIntent
from app.llm.factory import get_llm, is_configured
from app.llm.prompts.ask import PARSE
from app.services.ask import _context, _facts
from tests.conftest import SEED_TODAY

pytestmark = [
    pytest.mark.eval,
    pytest.mark.skipif(not is_configured(get_settings()), reason="Azure OpenAI not configured"),
]
Q = AskIntent

CASES = [
    ("What needs my attention this week?", Q.NEEDS_ME, None, None),
    ("who's free sunday?", Q.FREE_ON, None, "2026-10-11"),
    ("Who could cover for Anna on Sunday?", Q.REPLACE, "Anna", "2026-10-11"),
    ("anyone serving too much lately?", Q.SERVING_A_LOT, None, None),
    ("write reminders for this Sunday's team", Q.DRAFT_REMINDER, None, "2026-10-11"),
    (
        "Can you draft a note asking Christopher to help on Oct 18?",
        Q.DRAFT_MESSAGE,
        "Christopher",
        "2026-10-18",
    ),
    ("what do you know about Rachel", Q.REMEMBER, "Rachel", None),
    ("When is Megan away?", Q.AVAILABILITY, "Megan", None),
    ("Is Emily going through something at home?", Q.PRIVATE, "Emily", None),
    ("What's the weather on Sunday?", Q.UNKNOWN, None, None),
]


@pytest.mark.parametrize(("question", "intent", "person", "on"), CASES)
def test_parses_what_was_asked(
    session: Session,
    grace_id: uuid.UUID,
    question: str,
    intent: AskIntent,
    person: str | None,
    on: str | None,
) -> None:
    kids = session.scalar(
        select(Ministry.id).where(Ministry.church_id == grace_id, Ministry.name == "Kids")
    )
    sarah = session.scalar(
        select(Person.id).where(Person.church_id == grace_id, Person.name == "Sarah Collins")
    )
    assert kids and sarah
    ctx = _context(session, grace_id, kids, sarah, SEED_TODAY)
    parsed = get_llm().complete(system=PARSE, user=_facts(ctx, question), schema=ParsedQuestion)
    assert parsed.intent is intent
    assert parsed.person == person
    if on is not None:
        assert parsed.date == on
