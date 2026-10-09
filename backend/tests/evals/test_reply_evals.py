"""Reading volunteers' free-text replies with the real model (`uv run pytest -m eval tests/evals`).

Rules catch "1", "yes", "maybe", "stop"; these are the messages that reach the model.
"""

import pytest

from app.config import get_settings
from app.domain.replies import ParsedReply, ReplyIntent
from app.llm.factory import get_llm, is_configured
from app.llm.prompts.replies import PARSE

pytestmark = [
    pytest.mark.eval,
    pytest.mark.skipif(not is_configured(get_settings()), reason="Azure OpenAI not configured"),
]
R = ReplyIntent
FACTS = "Today: Thursday 2026-10-08\nThey were reminded about Sunday 2026-10-11.\n"

CASES = [
    ("Count me in!", R.CONFIRM, []),
    ("Unfortunately we have a family thing that day", R.DECLINE, []),
    ("I'll try but I might be working", R.MAYBE, []),
    ("I'm traveling Oct 18 to Oct 20", R.AWAY, ["2026-10-18", "2026-10-19", "2026-10-20"]),
    ("what do you have on file for me?", R.WHAT_I_KNOW, []),
    ("please don't message me anymore", R.STOP, []),
    ("Is the parking lot open on Sunday?", R.OTHER, []),
]


@pytest.mark.parametrize(("message", "intent", "dates"), CASES)
def test_reads_what_the_volunteer_meant(
    message: str, intent: ReplyIntent, dates: list[str]
) -> None:
    parsed = get_llm().complete(
        system=PARSE, user=f"{FACTS}\nMessage: {message}", schema=ParsedReply
    )
    assert parsed.intent is intent
    assert sorted(parsed.dates) == dates
