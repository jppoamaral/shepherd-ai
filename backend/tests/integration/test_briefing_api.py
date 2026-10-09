"""Weekly briefings and rosters over HTTP, on the seeded demo week at Grace."""

import pytest
from fastapi.testclient import TestClient

from tests.conftest import GRACE, RIVERSIDE

DEMO_WEEK = {"start": "2026-10-11"}


@pytest.fixture
def grace(client: TestClient) -> dict:
    cid = next(c["id"] for c in client.get("/churches").json() if c["name"] == GRACE)
    leaders = {leader["name"]: leader for leader in client.get(f"/churches/{cid}/leaders").json()}
    people = {p["name"]: p["id"] for p in client.get(f"/churches/{cid}/people").json()}
    ministries = {m["name"]: m["id"] for m in client.get(f"/churches/{cid}/ministries").json()}
    return {"id": cid, "leaders": leaders, "people": people, "ministries": ministries}


def briefing_for(client: TestClient, grace: dict, name: str) -> dict:
    pid = grace["leaders"][name]["person_id"]
    response = client.get(f"/churches/{grace['id']}/leaders/{pid}/briefing", params=DEMO_WEEK)
    assert response.status_code == 200, response.text
    return response.json()


def test_leaders_list_for_the_who_am_i_picker(grace: dict) -> None:
    sarah = grace["leaders"]["Sarah Collins"]
    assert sarah["ministries"] == [
        {
            "ministry_id": grace["ministries"]["Kids"],
            "ministry": "Kids",
            "can_schedule": True,
            "can_approve": True,
        }
    ]
    assert {m["ministry"] for m in grace["leaders"]["Mike Harris"]["ministries"]} == {
        "Hospitality",
        "Media",
    }


def test_sarah_sees_annas_double_booking_and_overload_but_not_hannahs(
    client: TestClient, grace: dict
) -> None:
    brief = briefing_for(client, grace, "Sarah Collins")
    texts = [i["text"] for i in brief["items"]]
    assert brief["headline"].startswith("Sarah, this week you have 2 warnings")
    overlap = next(i for i in brief["items"] if i["type"] == "overlap")
    assert overlap["text"].startswith("Anna Parker is booked twice at Sunday 9:30 Service")
    assert overlap["can_huddle"] is True  # shared with Worship's leader
    assert sorted(overlap["ministries"]) == ["Kids", "Worship"]
    assert any(t.startswith("Anna Parker is serving 4 times the week of 11 Oct") for t in texts)
    assert not any("Hannah" in t for t in texts)
    kids_930 = next(g for g in brief["gatherings"] if g["name"] == "Sunday 9:30 Service")
    assert (kids_930["ministry"], kids_930["needed"], kids_930["filled"]) == ("Kids", 4, 5)


def test_david_sees_both_double_bookings_and_worship_gaps(client: TestClient, grace: dict) -> None:
    brief = briefing_for(client, grace, "David Morales")
    overlaps = sorted(i["people"][0] for i in brief["items"] if i["type"] == "overlap")
    assert overlaps == ["Anna Parker", "Hannah Wright"]
    assert any(
        i["type"] == "below_minimum" and i["text"].startswith("Worship needs")
        for i in brief["items"]
    )
    assert not any(i["text"].startswith("Kids needs") for i in brief["items"])


def test_mike_hears_about_media_not_kids(client: TestClient, grace: dict) -> None:
    brief = briefing_for(client, grace, "Mike Harris")
    people = {p for i in brief["items"] for p in i["people"]}
    assert "Hannah Wright" in people  # Media approver, Wednesday clash
    assert "Anna Parker" not in people


def test_briefing_only_for_leaders_and_scoped_to_church(client: TestClient, grace: dict) -> None:
    rachel = grace["people"]["Rachel Turner"]
    assert client.get(f"/churches/{grace['id']}/leaders/{rachel}/briefing").status_code == 404
    river = next(c["id"] for c in client.get("/churches").json() if c["name"] == RIVERSIDE)
    sarah = grace["leaders"]["Sarah Collins"]["person_id"]
    assert client.get(f"/churches/{river}/leaders/{sarah}/briefing").status_code == 404


def test_roster_flags_anna_and_shows_gaps(client: TestClient, grace: dict) -> None:
    kids = grace["ministries"]["Kids"]
    roster = client.get(
        f"/churches/{grace['id']}/ministries/{kids}/roster",
        params={"start": "2026-10-11", "end": "2026-10-12"},
    ).json()
    assert [g["name"] for g in roster["gatherings"]] == [
        "Sunday 9:30 Service",
        "Sunday 11:00 Service",
    ]
    service_930 = {r["role"]: r for r in roster["gatherings"][0]["roles"]}
    anna = next(p for p in service_930["Helper"]["people"] if p["name"] == "Anna Parker")
    assert anna["flags"] == ["double_booked", "over_load"]
    assert anna["experience"] == "experienced"
    assert service_930["Helper"]["missing"] == 0
    service_1100 = {r["role"]: r for r in roster["gatherings"][1]["roles"]}
    assert service_1100["Helper"] == {**service_1100["Helper"], "people": [], "missing": 2}
    unknown = client.get(
        f"/churches/{grace['id']}/ministries/{grace['people']['Rachel Turner']}/roster"
    )
    assert unknown.status_code == 404
