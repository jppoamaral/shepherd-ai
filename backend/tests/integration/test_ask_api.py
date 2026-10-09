"""Ask Shepherd over HTTP on the seeded demo week (today pinned to Thu 8 Oct 2026)."""

import uuid
from collections.abc import Iterator
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.ask import ask_llm_dependency, today_dependency
from app.db.models import Assignment, MemoryItem, Message, Proposal
from app.domain.ask import ParsedQuestion
from app.domain.enums import AskIntent
from app.llm.fake import FakeLLM
from app.main import app
from tests.conftest import GRACE

TODAY = date(2026, 10, 8)
SUNDAY = "2026-10-11"


@pytest.fixture
def llm() -> Iterator[FakeLLM]:
    fake = FakeLLM()
    app.dependency_overrides[ask_llm_dependency] = lambda: fake
    yield fake
    app.dependency_overrides.pop(ask_llm_dependency, None)


@pytest.fixture
def grace(client: TestClient, llm: FakeLLM) -> Iterator[dict]:
    app.dependency_overrides[today_dependency] = lambda: TODAY
    cid = next(c["id"] for c in client.get("/churches").json() if c["name"] == GRACE)
    leaders = client.get(f"/churches/{cid}/leaders").json()
    ministries = {m["ministry"]: m["ministry_id"] for x in leaders for m in x["ministries"]}
    people = {p["name"]: p["id"] for p in client.get(f"/churches/{cid}/people").json()}
    yield {
        "id": cid,
        "leaders": {x["name"]: x["person_id"] for x in leaders},
        "kids": ministries["Kids"],
        "people": people,
    }
    app.dependency_overrides.pop(today_dependency, None)


def ask(client: TestClient, grace: dict, leader: str = "Sarah Collins", **body):  # type: ignore[no-untyped-def]
    return client.post(
        f"/churches/{grace['id']}/ministries/{grace['kids']}/ask",
        json={"person_id": grace["leaders"][leader], **body},
    )


def test_suggestions_use_this_weeks_real_data(client: TestClient, grace: dict) -> None:
    response = client.get(
        f"/churches/{grace['id']}/ministries/{grace['kids']}/ask",
        params={"person_id": grace["leaders"]["Sarah Collins"]},
    )
    assert response.status_code == 200, response.text
    start = response.json()
    assert start["greeting"] == "Hi Sarah. What can I help with?"
    assert [s["label"] for s in start["suggestions"]] == [
        "What needs me this week?",
        "Who can take Anna's place on Oct 11?",
        "Who is free on Oct 11?",
        "Who is serving a lot right now?",
        "Draft a reminder for Oct 11",
        "What do you remember about Rachel?",
    ]


def test_what_needs_me_lists_kids_findings_with_next_steps(client: TestClient, grace: dict) -> None:
    out = ask(client, grace, intent="needs_me").json()
    assert out["text"].endswith("you this week.")
    assert any("Anna Parker is booked twice" in n for n in out["notes"])
    labels = [a["label"] for a in out["actions"]]
    assert "Who can take Anna's place?" in labels and "Open the huddle" in labels
    assert out["source"] == "From this week's checks"


def test_who_can_take_annas_place_lists_free_helpers_only(client: TestClient, grace: dict) -> None:
    out = ask(
        client,
        grace,
        intent="replace",
        about_person_id=grace["people"]["Anna Parker"],
        on=SUNDAY,
    ).json()
    names = [p["name"] for p in out["people"]]
    assert names and out["text"].endswith("free for the Sunday 9:30 Service on Oct 11.")
    # Never Anna herself, and never anyone already serving at 9:30.
    assert not {"Anna Parker", "Emily Brooks", "Rachel Turner", "Sarah Collins"} & set(names)
    # Olivia is a veteran helper but blocked out that day: left out, with no reason given.
    assert "Olivia Grant" not in names
    assert out["notes"][0] == "Olivia can't make Oct 11, so I left them out."
    labels = [a["label"] for a in out["actions"]]
    assert labels[0] == f"Draft a message to {names[0].split(' ')[0]}"
    assert "Open the huddle" in labels
    assert out["source"] == "From the Oct 11 roster and availability"


def test_who_is_free_leaves_out_anyone_serving_or_blocked_out(
    client: TestClient, grace: dict, session: Session
) -> None:
    out = ask(client, grace, intent="free_on", on=SUNDAY).json()
    free_at_930 = {
        p["name"] for p in out["people"] if "9:30" in p["detail"] or p["detail"] == "Free all day"
    }
    assert not {"Anna Parker", "Emily Brooks", "Rachel Turner", "Megan Lee"} & free_at_930
    assert "Sarah Collins" not in {p["name"] for p in out["people"]}  # not the leader asking
    assert "Olivia can't make Sun Oct 11, so I left them out." in out["notes"]


def test_serving_a_lot_shows_annas_week_against_her_preference(
    client: TestClient, grace: dict
) -> None:
    out = ask(client, grace, intent="serving_a_lot").json()
    anna = next(p for p in out["people"] if p["name"] == "Anna Parker")
    assert anna["detail"] == "4 times this week · prefers 2 a week"
    assert "That's above Anna's preferred 2 a week." in out["notes"]


def test_reminders_are_drafted_for_everyone_but_the_leader(client: TestClient, grace: dict) -> None:
    out = ask(client, grace, intent="draft_reminder", on=SUNDAY).json()
    assert {d["to"] for d in out["drafts"]} == {
        "Anna Parker",
        "Emily Brooks",
        "Rachel Turner",
        "Megan Lee",
    }
    rachel = next(d for d in out["drafts"] if d["to"] == "Rachel Turner")
    assert rachel["body"].startswith("Hi Rachel, a friendly reminder that you're serving as Helper")
    assert rachel["body"].endswith("Thank you, Sarah")


def test_draft_message_asks_one_person_one_to_one(client: TestClient, grace: dict) -> None:
    out = ask(
        client,
        grace,
        intent="draft_message",
        about_person_id=grace["people"]["Anna Peterson"],
        on=SUNDAY,
    ).json()
    (draft,) = out["drafts"]
    assert draft["to"] == "Anna Peterson"
    assert draft["body"].startswith("Hi Anna, could you serve with Kids on Sun Oct 11 at 9:30 AM?")


def test_remember_shows_confirmed_memories_and_pending_ones(
    client: TestClient, grace: dict
) -> None:
    out = ask(client, grace, intent="remember", about_person_id=grace["people"]["Rachel Turner"])
    notes = out.json()["notes"]
    assert "You always pair Emily with Rachel." in notes
    assert "Waiting for you to confirm: “Rachel is ready to lead a class.”" in notes


def test_personal_reasons_are_refused_before_the_model_sees_them(
    client: TestClient, grace: dict, llm: FakeLLM
) -> None:
    for question in ("Why is Emily taking time off?", "Is Emily sick?"):
        out = ask(client, grace, question=question).json()
        assert out["refused"] is True and out["intent"] == "private"
        assert out["text"].endswith("That's Emily's to share.")
        assert out["actions"][0]["label"] == "Check Emily's availability"
    assert llm.calls == []  # never sent to the model


def test_a_typed_question_is_parsed_then_answered_from_the_record(
    client: TestClient, grace: dict, llm: FakeLLM
) -> None:
    llm.queue(ParsedQuestion(intent=AskIntent.REPLACE, person="Anna", date=SUNDAY))
    out = ask(client, grace, question="who could cover for anna on sunday?").json()
    # Two Annas on Kids: ask which, never guess.
    assert out["text"] == "Which Anna do you mean?"
    assert [a["label"] for a in out["actions"]] == ["Anna Parker", "Anna Peterson"]
    assert "Today: Thursday 2026-10-08" in llm.calls[0]["user"]

    llm.queue(ParsedQuestion(intent=AskIntent.AVAILABILITY, person="Megan", date=None))
    out = ask(client, grace, question="when is megan away?").json()
    assert out["text"] == "Megan is blocked out Oct 19."


def test_answers_stay_inside_the_leaders_own_ministry(client: TestClient, grace: dict) -> None:
    assert ask(client, grace, leader="David Morales", intent="needs_me").status_code == 403
    out = ask(
        client, grace, intent="availability", about_person_id=grace["people"]["Hannah Wright"]
    ).json()
    assert out["text"] == "That person isn't on the Kids team."


def test_typed_questions_need_the_model_but_suggestions_dont(
    client: TestClient, grace: dict
) -> None:
    app.dependency_overrides[ask_llm_dependency] = lambda: None
    out = ask(client, grace, question="who is around next week?").json()
    assert out["text"].startswith("I can only answer the suggested questions right now.")
    assert out["actions"]
    assert ask(client, grace, intent="serving_a_lot").status_code == 200


def test_hi_and_thanks_are_answered_without_the_model(client: TestClient, grace: dict) -> None:
    app.dependency_overrides[ask_llm_dependency] = lambda: None
    out = ask(client, grace, question="hi").json()
    assert out["text"] == "Hi Sarah! Ask me in your own words, or start with one of these."
    assert out["actions"]
    out = ask(client, grace, question="Good morning, Shepherd!").json()
    assert out["text"].startswith("Hi Sarah!")
    out = ask(client, grace, question="thanks!").json()
    assert out["text"] == "You're welcome. Anything else?"


def test_asking_never_writes_to_the_record(
    client: TestClient, grace: dict, session: Session
) -> None:
    def counts() -> tuple[int | None, ...]:
        church = uuid.UUID(grace["id"])
        return tuple(
            session.scalar(select(func.count()).where(model.church_id == church))
            for model in (Assignment, Proposal, Message, MemoryItem)
        )

    before = counts()
    for intent in ("needs_me", "free_on", "serving_a_lot", "draft_reminder"):
        assert ask(client, grace, intent=intent).status_code == 200
    ask(client, grace, intent="draft_message", about_person_id=grace["people"]["Emily Brooks"])
    assert counts() == before
