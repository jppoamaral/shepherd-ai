"""Roster suggestion over HTTP on Grace's seed."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Assignment, AuditLog
from app.domain.enums import AssignmentSource
from tests.conftest import GRACE


@pytest.fixture
def grace(client: TestClient) -> dict:
    cid = next(c["id"] for c in client.get("/churches").json() if c["name"] == GRACE)
    leaders = {x["name"]: x["person_id"] for x in client.get(f"/churches/{cid}/leaders").json()}
    ministries = {m["name"]: m["id"] for m in client.get(f"/churches/{cid}/ministries").json()}
    people = {p["name"]: p["id"] for p in client.get(f"/churches/{cid}/people").json()}
    return {"id": cid, "leaders": leaders, "ministries": ministries, "people": people}


def get_suggestion(client: TestClient, grace: dict) -> dict:
    path = f"/churches/{grace['id']}/ministries/{grace['ministries']['Kids']}/suggestion"
    response = client.get(path, params={"start": "2026-10-11"})
    assert response.status_code == 200, response.text
    return response.json()


def test_suggestion_fills_open_places_with_reasons_and_never_double_books(
    client: TestClient, grace: dict
) -> None:
    s = get_suggestion(client, grace)
    assert s["ministry"] == "Kids" and s["lines"]
    assert all(line["reason"] for line in s["lines"])
    # 9:30 on Oct 11 is already staffed by the seed; Anna is never added at a time she's busy.
    taken = {(line["start_at"], line["person_id"]) for line in s["lines"] if line["person_id"]}
    assert len(taken) == len([line for line in s["lines"] if line["person_id"]])
    anna = grace["people"]["Anna Parker"]
    assert not any(
        line["person_id"] == anna and line["start_at"].startswith("2026-10-11T09:30")
        for line in s["lines"]
    )


def test_approving_an_edited_suggestion_records_it_through_approval(
    client: TestClient, grace: dict, session: Session
) -> None:
    s = get_suggestion(client, grace)
    first = next(line for line in s["lines"] if line["person_id"] and line["alternatives"])
    swapped = first["alternatives"][0]
    chosen = [
        {
            "gathering_id": first["gathering_id"],
            "role_id": first["role_id"],
            "person_id": swapped["person_id"],
            "reason": "Leader's choice",
        }
    ]
    path = f"/churches/{grace['id']}/ministries/{grace['ministries']['Kids']}/suggestion/approve"

    rachel = grace["people"]["Rachel Turner"]
    assert client.post(path, json={"person_id": rachel, "assignments": chosen}).status_code == 403

    approved = client.post(
        path, json={"person_id": grace["leaders"]["Sarah Collins"], "assignments": chosen}
    )
    assert approved.status_code == 200, approved.text
    proposal = approved.json()
    assert proposal["status"] == "approved" and proposal["created_by_agent"] == "roster"
    row = session.scalars(
        select(Assignment).where(
            Assignment.person_id == swapped["person_id"],
            Assignment.gathering_id == first["gathering_id"],
        )
    ).one()
    assert (row.source, row.reason) == (AssignmentSource.SUGGESTION, "Leader's choice")
    assert session.scalars(select(AuditLog).where(AuditLog.target_id == proposal["id"])).one()
