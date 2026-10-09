"""Schedule intake over HTTP, with FakeLLM and a pinned date."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.api.intake import today_dependency
from app.api.onboarding import llm_dependency
from app.domain.enums import Weekday
from app.domain.intake import NicknameSuggestions, ParsedEntry, ParsedSchedule
from app.llm.fake import FakeLLM
from app.main import app
from tests.conftest import GRACE, RIVERSIDE, SEED_TODAY


@pytest.fixture
def llm(client: TestClient) -> Iterator[FakeLLM]:
    fake = FakeLLM()
    app.dependency_overrides[llm_dependency] = lambda: fake
    app.dependency_overrides[today_dependency] = lambda: SEED_TODAY
    yield fake
    app.dependency_overrides.pop(llm_dependency, None)
    app.dependency_overrides.pop(today_dependency, None)


def ids(client: TestClient, church: str = GRACE) -> tuple[str, str, dict[str, str]]:
    cid = next(c["id"] for c in client.get("/churches").json() if c["name"] == church)
    kids = next(
        m["id"] for m in client.get(f"/churches/{cid}/ministries").json() if m["name"] == "Kids"
    )
    people = {p["name"]: p["id"] for p in client.get(f"/churches/{cid}/people").json()}
    return cid, kids, people


def parsed(*names: str) -> ParsedSchedule:
    return ParsedSchedule(
        entries=[
            ParsedEntry(
                date="2026-10-11",
                weekday=Weekday.SUNDAY,
                time="09:30",
                gathering=None,
                all_gatherings_that_day=False,
                role_as_written="helpers",
                role="Helper",
                names=list(names),
            )
        ],
        clarifying_question=None,
    )


def test_submit_answer_and_approve_over_http(client: TestClient, llm: FakeLLM) -> None:
    cid, kids, people = ids(client)
    sarah = people["Sarah Collins"]
    llm.queue(parsed("Rachel", "Anna P."))

    submitted = client.post(
        f"/churches/{cid}/ministries/{kids}/intake", json={"person_id": sarah, "text": "..."}
    )
    assert submitted.status_code == 201, submitted.text
    intake = submitted.json()
    assert intake["status"] == "needs_answers"
    (question,) = intake["questions"]
    assert question["kind"] == "ambiguous_name" and question["subject"] == "Anna P."

    parker = next(c["id"] for c in question["choices"] if c["label"] == "Anna Parker")
    answered = client.post(
        f"/churches/{cid}/intake/{intake['id']}/answers",
        json={"person_id": sarah, "question_id": question["id"], "choice_id": parker},
    ).json()
    assert answered["status"] == "proposed" and answered["questions"] == []
    assert "Anna Parker" in answered["summary"]

    approve = f"/churches/{cid}/proposals/{answered['proposal_id']}/approve"
    assert client.post(approve, json={"person_id": sarah}).json()["status"] == "approved"
    assert client.get(f"/churches/{cid}/intake/{intake['id']}").json()["status"] == "approved"

    late = client.post(
        f"/churches/{cid}/intake/{intake['id']}/answers",
        json={"person_id": sarah, "question_id": question["id"], "choice_id": parker},
    )
    assert late.status_code == 409


def test_errors_map_to_clear_statuses(client: TestClient, llm: FakeLLM) -> None:
    cid, kids, people = ids(client)
    path = f"/churches/{cid}/ministries/{kids}/intake"

    not_scheduler = client.post(path, json={"person_id": people["Rachel Turner"], "text": "..."})
    assert not_scheduler.status_code == 403

    llm.queue(ParsedSchedule(entries=[], clarifying_question="Is this the Kids schedule?"))
    unreadable = client.post(path, json={"person_id": people["Sarah Collins"], "text": "hi"})
    assert unreadable.status_code == 422 and "Kids schedule" in unreadable.json()["detail"]

    llm.queue(parsed("Jessie"))
    llm.queue(NicknameSuggestions(suggestions=[]))
    intake = client.post(path, json={"person_id": people["Sarah Collins"], "text": "..."}).json()
    bad = client.post(
        f"/churches/{cid}/intake/{intake['id']}/answers",
        json={"person_id": people["Sarah Collins"], "question_id": "q1", "choice_id": "c999"},
    )
    assert bad.status_code == 422


def test_intakes_are_scoped_to_their_church(client: TestClient, llm: FakeLLM) -> None:
    cid, kids, people = ids(client)
    llm.queue(parsed("Rachel"))
    intake = client.post(
        f"/churches/{cid}/ministries/{kids}/intake",
        json={"person_id": people["Sarah Collins"], "text": "."},
    ).json()
    river, river_kids, _ = ids(client, RIVERSIDE)
    assert client.get(f"/churches/{river}/intake/{intake['id']}").status_code == 404
    # Grace's scheduler can't submit for another church's ministry.
    other = client.post(
        f"/churches/{cid}/ministries/{river_kids}/intake",
        json={"person_id": people["Sarah Collins"], "text": "."},
    )
    assert other.status_code == 404


def test_approval_queue_describes_a_roster_in_plain_language(
    client: TestClient, llm: FakeLLM
) -> None:
    cid, kids, people = ids(client)
    llm.queue(parsed("Rachel", "Emily"))
    intake = client.post(
        f"/churches/{cid}/ministries/{kids}/intake",
        json={"person_id": people["Sarah Collins"], "text": "."},
    ).json()
    (pending,) = [
        p
        for p in client.get(f"/churches/{cid}/proposals", params={"status": "pending"}).json()
        if p["id"] == intake["proposal_id"]
    ]
    assert pending["title"] == "Kids roster (2 assignments)"
    assert pending["summary"].splitlines() == [
        "• Sunday 9:30 Service, Sun 11 Oct 9:30 AM · Helper · Rachel Turner",
        "• Sunday 9:30 Service, Sun 11 Oct 9:30 AM · Helper · Emily Brooks",
    ]
