"""Onboarding and the approval queue over HTTP, with FakeLLM standing in for the model."""

import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.onboarding import llm_dependency
from app.config import Settings
from app.db.models import Person
from app.domain.profile import ReviewReply
from app.llm import factory
from app.llm.fake import FakeLLM
from app.main import app
from tests.conftest import GRACE
from tests.profile_script import DONE, SCRIPT, THREE_WEEKS


@pytest.fixture
def llm(client: TestClient) -> Iterator[FakeLLM]:
    fake = FakeLLM()
    app.dependency_overrides[llm_dependency] = lambda: fake
    yield fake
    app.dependency_overrides.pop(llm_dependency, None)


def start(client: TestClient, name: str = "Hope Chapel") -> dict:
    response = client.post("/onboarding", json={"church_name": name, "admin_name": "Pat Admin"})
    assert response.status_code == 201, response.text
    return response.json()


def chat(client: TestClient, llm: FakeLLM, started: dict, reply, text: str = "…") -> dict:  # type: ignore[no-untyped-def]
    llm.queue(reply)
    path = f"/churches/{started['church_id']}/onboarding/{started['onboarding_id']}/messages"
    response = client.post(path, json={"text": text})
    assert response.status_code == 200, response.text
    return response.json()


def test_start_creates_a_draft_church_and_asks_the_first_question(client: TestClient) -> None:
    started = start(client)
    assert started["topic"] == "basics"
    assert "time zone" in started["message"]
    church = client.get(f"/churches/{started['church_id']}").json()
    assert church["profile_status"] == "draft"


def test_a_church_name_can_only_be_used_once(client: TestClient) -> None:
    response = client.post("/onboarding", json={"church_name": GRACE, "admin_name": "Someone"})
    assert response.status_code == 409


def test_chat_to_proposal_to_approval_over_http(client: TestClient, llm: FakeLLM) -> None:
    started = start(client)
    cid = started["church_id"]
    for _, reply in SCRIPT:
        answer = chat(client, llm, started, reply)
    assert answer["topic"] == "review"

    proposed = chat(client, llm, started, ReviewReply(change_topic=None, **DONE), "Looks right")
    assert proposed["status"] == "proposed"

    pending = client.get(f"/churches/{cid}/proposals", params={"status": "pending"}).json()
    assert [p["id"] for p in pending] == [proposed["proposal_id"]]
    assert pending[0]["type"] == "church_profile"

    approve = f"/churches/{cid}/proposals/{proposed['proposal_id']}/approve"
    response = client.post(approve, json={"person_id": started["admin_person_id"]})
    assert response.status_code == 200 and response.json()["status"] == "approved"

    church = client.get(f"/churches/{cid}").json()
    assert church["profile_status"] == "approved"
    assert church["timezone"] == "America/Chicago"
    gathering_types = {t["name"]: t for t in client.get(f"/churches/{cid}/gathering-types").json()}
    assert gathering_types["Wednesday Prayer"]["weekday"] == "wednesday"
    assert gathering_types["Christmas Eve"]["kind"] == "special"

    again = client.post(approve, json={"person_id": started["admin_person_id"]})
    assert again.status_code == 409


def test_only_an_admin_may_approve(client: TestClient, llm: FakeLLM, session: Session) -> None:
    started = start(client)
    for _, reply in SCRIPT:
        chat(client, llm, started, reply)
    proposed = chat(client, llm, started, ReviewReply(change_topic=None, **DONE))
    approve = f"/churches/{started['church_id']}/proposals/{proposed['proposal_id']}/approve"

    volunteer = Person(church_id=uuid.UUID(started["church_id"]), name="Not An Admin")
    session.add(volunteer)
    session.flush()
    assert client.post(approve, json={"person_id": str(volunteer.id)}).status_code == 403

    grace = next(c for c in client.get("/churches").json() if c["name"] == GRACE)
    outsider = client.get(f"/churches/{grace['id']}/people").json()[0]["id"]
    assert client.post(approve, json={"person_id": outsider}).status_code == 404


def test_sample_endpoint_returns_suggestions(client: TestClient, llm: FakeLLM) -> None:
    started = start(client)
    chat(client, llm, started, SCRIPT[0][1])
    llm.queue(THREE_WEEKS)
    path = f"/churches/{started['church_id']}/onboarding/{started['onboarding_id']}/sample"
    reply = client.post(path, json={"text": "Wed 2 Sep: Keys - Anna"}).json()
    assert "From the sample I found" in reply["message"]

    state = client.get(
        f"/churches/{started['church_id']}/onboarding/{started['onboarding_id']}"
    ).json()
    assert "Wednesday 7:00 PM: every Wednesday at 7:00 PM" in state["summary"]


def test_onboarding_ids_are_scoped_to_their_church(client: TestClient, llm: FakeLLM) -> None:
    started = start(client)
    grace = next(c for c in client.get("/churches").json() if c["name"] == GRACE)
    response = client.get(f"/churches/{grace['id']}/onboarding/{started['onboarding_id']}")
    assert response.status_code == 404


def test_messages_need_a_configured_model(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        factory,
        "get_settings",
        lambda: Settings(
            azure_openai_endpoint="", azure_openai_api_key="", azure_openai_deployment=""
        ),
    )
    started = start(client)
    path = f"/churches/{started['church_id']}/onboarding/{started['onboarding_id']}/messages"
    response = client.post(path, json={"text": "We're in Dallas"})
    assert response.status_code == 503
    assert "AZURE_OPENAI" in response.json()["detail"]
