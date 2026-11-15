"""Roster suggestion over HTTP on Grace's seed."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Assignment, AuditLog, Finding
from app.domain.enums import AssignmentSource, FindingStatus, FindingType
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


def test_an_edit_that_double_books_is_flagged_before_approval_and_found_after(
    client: TestClient, grace: dict, session: Session
) -> None:
    """Brief section 11: the checks re-run on the leader's edited roster."""
    s = get_suggestion(client, grace)
    filled = [line for line in s["lines"] if line["person_id"]]
    first, second = next(
        (a, b)
        for a in filled
        for b in filled
        if a["gathering_id"] == b["gathering_id"] and a["person_id"] != b["person_id"]
    )
    # The leader's edit: the same person in both places at one gathering.
    chosen = [
        {
            "gathering_id": x["gathering_id"],
            "role_id": x["role_id"],
            "person_id": first["person_id"],
        }
        for x in (first, second)
    ]
    body = {"person_id": grace["leaders"]["Sarah Collins"], "assignments": chosen}
    base = f"/churches/{grace['id']}/ministries/{grace['ministries']['Kids']}/suggestion"

    def overlap_findings() -> list[Finding]:
        found = session.scalars(
            select(Finding).where(
                Finding.type == FindingType.OVERLAP,
                Finding.status == FindingStatus.OPEN,
                Finding.gathering_id == first["gathering_id"],
            )
        )
        return [f for f in found if first["person_id"] in map(str, f.person_ids)]

    # As suggested, the roster raises no double booking.
    untouched = [
        {k: x[k] for k in ("gathering_id", "role_id", "person_id")} for x in (first, second)
    ]
    plain = client.post(f"{base}/check", json={**body, "assignments": untouched})
    assert plain.status_code == 200, plain.text
    assert not [w for w in plain.json()["warnings"] if w["type"] == "overlap"]

    checked = client.post(f"{base}/check", json=body)
    assert checked.status_code == 200, checked.text
    warnings = [w for w in checked.json()["warnings"] if w["type"] == "overlap"]
    assert len(warnings) == 1 and first["name"] in warnings[0]["text"]
    assert "booked twice" in warnings[0]["text"]
    # Checking saves nothing, and the warning doesn't block approval.
    assert not overlap_findings()
    assert client.post(f"{base}/approve", json=body).status_code == 200
    assert len(overlap_findings()) == 1
