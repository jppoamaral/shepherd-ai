"""Leader memory over HTTP (brief §6 and §11 memory rows) on Grace's seed."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AuditLog, MemoryItem, Proposal
from tests.conftest import GRACE


@pytest.fixture
def grace(client: TestClient) -> dict:
    cid = next(c["id"] for c in client.get("/churches").json() if c["name"] == GRACE)
    leaders = {x["name"]: x["person_id"] for x in client.get(f"/churches/{cid}/leaders").json()}
    people = {p["name"]: p["id"] for p in client.get(f"/churches/{cid}/people").json()}
    ministries = {m["name"]: m["id"] for m in client.get(f"/churches/{cid}/ministries").json()}
    base = f"/churches/{cid}/ministries/{ministries['Kids']}/memory"
    return {"id": cid, "leaders": leaders, "people": people, "base": base}


def test_kids_memory_shows_confirmed_items_and_the_pending_question(
    client: TestClient, grace: dict
) -> None:
    memory = client.get(grace["base"]).json()
    assert [(m["kind"], m["text"], m["about"], m["confirmed_by"]) for m in memory["items"]] == [
        ("habit", "You always pair Emily with Rachel.", "Rachel Turner", "Sarah Collins"),
        ("preference", "Emily prefers the 9:30 service.", "Emily Brooks", "Sarah Collins"),
    ]
    (pending,) = memory["pending"]
    assert pending["question"] == "Should I remember this? “Rachel is ready to lead a class.”"


def test_a_note_is_proposed_then_saved_only_after_confirmation(
    client: TestClient, grace: dict, session: Session
) -> None:
    sarah = grace["leaders"]["Sarah Collins"]
    pending = client.post(
        f"{grace['base']}/notes",
        json={"person_id": sarah, "text": "Megan likes check-in duty.", "kind": "preference"},
    ).json()
    assert len(client.get(grace["base"]).json()["items"]) == 2  # nothing saved yet

    queue = client.get(f"/churches/{grace['id']}/proposals", params={"status": "pending"}).json()
    proposal = next(p for p in queue if p["id"] == pending["proposal_id"])
    assert proposal["title"] == "Should I remember this? (Kids)"
    assert proposal["summary"] == "“Megan likes check-in duty.”"

    approved = client.post(
        f"/churches/{grace['id']}/proposals/{proposal['id']}/approve", json={"person_id": sarah}
    )
    assert approved.json()["status"] == "approved"
    texts = [m["text"] for m in client.get(grace["base"]).json()["items"]]
    assert "Megan likes check-in duty." in texts
    entry = session.scalars(select(AuditLog).where(AuditLog.target_id == proposal["id"])).one()
    assert entry.action == "proposal.approved"


def test_health_or_family_notes_are_never_proposed(
    client: TestClient, grace: dict, session: Session
) -> None:
    before = len(session.scalars(select(Proposal)).all())
    response = client.post(
        f"{grace['base']}/notes",
        json={
            "person_id": grace["leaders"]["Sarah Collins"],
            "text": "Anna's mom is in the hospital.",
        },
    )
    assert response.status_code == 422
    assert "hospital" not in response.json()["detail"]  # the refusal doesn't repeat the detail
    assert len(session.scalars(select(Proposal)).all()) == before


def test_only_the_ministrys_leaders_add_or_delete(client: TestClient, grace: dict) -> None:
    rachel = grace["people"]["Rachel Turner"]
    assert (
        client.post(f"{grace['base']}/notes", json={"person_id": rachel, "text": "x"}).status_code
        == 403
    )
    item = client.get(grace["base"]).json()["items"][0]
    david = grace["leaders"]["David Morales"]
    assert (
        client.delete(f"{grace['base']}/{item['id']}", params={"person_id": david}).status_code
        == 403
    )


def test_deleting_a_memory_takes_effect_and_is_logged(
    client: TestClient, grace: dict, session: Session
) -> None:
    item = client.get(grace["base"]).json()["items"][0]
    sarah = grace["leaders"]["Sarah Collins"]
    assert (
        client.delete(f"{grace['base']}/{item['id']}", params={"person_id": sarah}).status_code
        == 204
    )
    assert item["id"] not in [m["id"] for m in client.get(grace["base"]).json()["items"]]
    assert session.scalar(select(MemoryItem).where(MemoryItem.id == item["id"])) is None
    entry = session.scalars(select(AuditLog).where(AuditLog.target_id == item["id"])).one()
    assert entry.action == "memory.deleted" and entry.before == {
        "kind": "habit",
        "text": item["text"],
    }
    assert (
        client.delete(f"{grace['base']}/{item['id']}", params={"person_id": sarah}).status_code
        == 404
    )
