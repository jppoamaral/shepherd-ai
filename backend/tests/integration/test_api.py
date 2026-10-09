"""Read-only endpoints and the published OpenAPI schema."""

import uuid
from datetime import datetime

from fastapi.testclient import TestClient

from tests.conftest import GRACE, RIVERSIDE


def test_health(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


def test_churches_show_their_different_load_rules(client: TestClient) -> None:
    churches = {c["name"]: c for c in client.get("/churches").json()}
    assert set(churches) == {GRACE, RIVERSIDE}
    assert churches[GRACE]["load_rules"] == [
        {"period": "week", "normal_max": 1, "warning_above": 2}
    ]
    assert churches[RIVERSIDE]["load_rules"] == [
        {"period": "month", "normal_max": 2, "warning_above": 2}
    ]
    assert churches[GRACE]["timezone"] == "America/Chicago"
    assert churches[RIVERSIDE]["timezone"] == "America/Los_Angeles"


def test_ministries_include_roles_minimums_and_leaders(
    client: TestClient, grace_id: uuid.UUID
) -> None:
    ministries = {m["name"]: m for m in client.get(f"/churches/{grace_id}/ministries").json()}
    kids = ministries["Kids"]
    assert {r["name"] for r in kids["roles"]} == {"Lead Teacher", "Helper", "Check-in"}
    helper = next(r for r in kids["roles"] if r["name"] == "Helper")
    assert {m["minimum"] for m in helper["minimums"]} == {2}
    assert kids["leaders"] == [
        {
            "person_id": kids["leaders"][0]["person_id"],
            "name": "Sarah Collins",
            "can_schedule": True,
            "can_approve": True,
        }
    ]
    media_duties = {
        (lead["name"], lead["can_schedule"], lead["can_approve"])
        for lead in ministries["Media"]["leaders"]
    }
    assert media_duties == {("Tom Becker", True, False), ("Mike Harris", False, True)}


def test_people_include_memberships_and_experience(client: TestClient, grace_id: uuid.UUID) -> None:
    people = {p["name"]: p for p in client.get(f"/churches/{grace_id}/people").json()}
    rachel = people["Rachel Turner"]
    assert [
        (m["ministry"], [(r["role"], r["experience"]) for r in m["roles"]])
        for m in rachel["memberships"]
    ] == [("Kids", [("Helper", "new")])]


def test_gatherings_are_shown_in_church_local_time(
    client: TestClient, grace_id: uuid.UUID, riverside_id: uuid.UUID
) -> None:
    window = {"from": "2026-10-11T00:00:00+00:00", "to": "2026-10-19T00:00:00+00:00"}
    grace = client.get(f"/churches/{grace_id}/gatherings", params=window).json()
    sunday = next(g for g in grace if g["name"] == "Sunday 9:30 Service")
    assert sunday["start_at"] == "2026-10-11T09:30:00-05:00"
    assert sunday["end_at"] == "2026-10-11T10:45:00-05:00"

    river = client.get(f"/churches/{riverside_id}/gatherings", params=window).json()
    friday = next(g for g in river if g["name"] == "Friday Youth Night")
    assert (
        datetime.fromisoformat(friday["start_at"]).strftime("%A %H:%M %z") == "Friday 19:00 -0700"
    )


def test_gatherings_reject_an_inverted_window(client: TestClient, grace_id: uuid.UUID) -> None:
    params = {"from": "2026-11-01T00:00:00Z", "to": "2026-10-01T00:00:00Z"}
    assert client.get(f"/churches/{grace_id}/gatherings", params=params).status_code == 422


def test_openapi_schema_is_published(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    assert {"/health", "/churches", "/churches/{church_id}/people"} <= set(schema["paths"])
    assert "ChurchOut" in schema["components"]["schemas"]


def test_only_known_endpoints_write(client: TestClient) -> None:
    """Writes go through onboarding or intake (which only propose) or ApprovalService."""
    schema = client.get("/openapi.json").json()
    writes = {
        (method, path)
        for path, methods in schema["paths"].items()
        for method in methods
        if method != "get"
    }
    assert writes == {
        ("post", "/onboarding"),
        ("post", "/churches/{church_id}/onboarding/{onboarding_id}/messages"),
        ("post", "/churches/{church_id}/onboarding/{onboarding_id}/sample"),
        ("post", "/churches/{church_id}/proposals/{proposal_id}/approve"),
        ("post", "/churches/{church_id}/proposals/{proposal_id}/reject"),
        ("post", "/churches/{church_id}/ministries/{ministry_id}/intake"),
        ("post", "/churches/{church_id}/intake/{intake_id}/answers"),
    }
