"""Conflict huddle over HTTP on the seeded demo week (clock pinned to Thu 8 Oct 6 PM)."""

from collections.abc import Iterator
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from app.api.huddles import now_dependency
from app.main import app
from tests.conftest import GRACE

NOW = datetime(2026, 10, 8, 18, 0, tzinfo=ZoneInfo("America/Chicago"))


@pytest.fixture
def grace(client: TestClient) -> Iterator[dict]:
    app.dependency_overrides[now_dependency] = lambda: NOW
    cid = next(c["id"] for c in client.get("/churches").json() if c["name"] == GRACE)
    leaders = {x["name"]: x["person_id"] for x in client.get(f"/churches/{cid}/leaders").json()}
    people = {p["name"]: p["id"] for p in client.get(f"/churches/{cid}/people").json()}
    yield {"id": cid, "leaders": leaders, "people": people}
    app.dependency_overrides.pop(now_dependency, None)


def overlap_for(client: TestClient, grace: dict, leader: str, volunteer: str) -> str:
    brief = client.get(
        f"/churches/{grace['id']}/leaders/{grace['leaders'][leader]}/briefing",
        params={"start": "2026-10-11"},
    ).json()
    return next(
        i["finding_id"]
        for i in brief["items"]
        if i["type"] == "overlap" and volunteer in i["people"]
    )


def start(client: TestClient, grace: dict, finding: str, leader: str):  # type: ignore[no-untyped-def]
    return client.post(
        f"/churches/{grace['id']}/findings/{finding}/huddle",
        json={"person_id": grace["leaders"][leader]},
    )


def test_sarah_and_david_get_saturday_slots_and_a_neutral_agenda(
    client: TestClient, grace: dict
) -> None:
    finding = overlap_for(client, grace, "Sarah Collins", "Anna Parker")
    response = start(client, grace, finding, "Sarah Collins")
    assert response.status_code == 201, response.text
    huddle = response.json()

    assert [x["name"] for x in huddle["leaders"]] == ["Sarah Collins", "David Morales"]
    assert [s["label"] for s in huddle["slots"]] == [
        "Sat 10 Oct, 10:00 AM to 10:15 AM",
        "Sat 10 Oct, 10:30 AM to 10:45 AM",
        "Sat 10 Oct, 11:00 AM to 11:15 AM",
    ]
    agenda = huddle["agenda"]
    assert agenda["volunteer"] == "Anna Parker"
    assert agenda["overlap"] == "Sun 11 Oct, 9:30 AM to 10:45 AM"
    kids, worship = agenda["sides"]
    assert (kids["ministry"], kids["role"], kids["leader"]) == ("Kids", "Helper", "Sarah Collins")
    assert (worship["ministry"], worship["role"], worship["leader"]) == (
        "Worship",
        "Keys",
        "David Morales",
    )
    # One suggestion per side, from that leader's own team, never Anna or anyone busy at 9:30.
    busy = {
        "Anna Parker",
        "Emily Brooks",
        "Rachel Turner",
        "Sarah Collins",
        "Megan Lee",
        "David Morales",
    }
    assert kids["replacement"] and kids["replacement"] not in busy
    assert worship["replacement"] and worship["replacement"] not in busy
    assert "Anna Parker isn't part of this conversation" in huddle["agenda_text"]

    again = start(client, grace, finding, "David Morales").json()
    assert again["id"] == huddle["id"]  # one open huddle per conflict


def test_choose_a_slot_then_resolve_rechecks_without_reassigning(
    client: TestClient, grace: dict
) -> None:
    finding = overlap_for(client, grace, "Sarah Collins", "Anna Parker")
    huddle = start(client, grace, finding, "Sarah Collins").json()
    base = f"/churches/{grace['id']}/huddles/{huddle['id']}"

    chosen = client.post(
        f"{base}/choose", json={"person_id": grace["leaders"]["David Morales"], "slot_id": "s2"}
    )
    assert chosen.json()["status"] == "scheduled"
    assert chosen.json()["chosen_slot"]["label"] == "Sat 10 Oct, 10:30 AM to 10:45 AM"

    resolved = client.post(
        f"{base}/resolve",
        json={
            "person_id": grace["leaders"]["Sarah Collins"],
            "outcome": "Anna stays on keys; Kids finds cover.",
        },
    ).json()
    assert resolved["status"] == "resolved" and resolved["outcome"].startswith("Anna stays")
    # Shepherd didn't move anyone, so the double booking is still there until a roster changes.
    assert resolved["finding_status"] == "open"


def test_only_warned_leaders_can_start_and_only_the_two_can_act(
    client: TestClient, grace: dict
) -> None:
    hannah_clash = overlap_for(client, grace, "David Morales", "Hannah Wright")
    assert (
        start(client, grace, hannah_clash, "Sarah Collins").status_code == 403
    )  # not her conflict
    anna_clash = overlap_for(client, grace, "Sarah Collins", "Anna Parker")
    huddle = start(client, grace, anna_clash, "Sarah Collins").json()
    outsider = grace["leaders"]["Linda Shaw"]
    choose = client.post(
        f"/churches/{grace['id']}/huddles/{huddle['id']}/choose",
        json={"person_id": outsider, "slot_id": "s1"},
    )
    assert choose.status_code == 403


def test_no_common_window_says_so_and_lists_nearest_options(
    client: TestClient, grace: dict
) -> None:
    hannah_clash = overlap_for(client, grace, "David Morales", "Hannah Wright")
    huddle = start(client, grace, hannah_clash, "David Morales").json()
    assert [x["name"] for x in huddle["leaders"]] == ["David Morales", "Tom Becker"]
    assert huddle["no_common_slot"] is True and huddle["slots"] == []
    assert any(o.startswith("David Morales is free") for o in huddle["nearest_options"])
    assert any(o.startswith("Tom Becker is free") for o in huddle["nearest_options"])
