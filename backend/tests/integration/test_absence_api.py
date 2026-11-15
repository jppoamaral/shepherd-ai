"""The absence check-in on the seeded demo week at Grace (brief §5, §11)."""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AuditLog, Membership
from app.domain.enums import MembershipStatus
from tests.conftest import GRACE

DEMO_WEEK = {"start": "2026-10-11"}


@pytest.fixture
def grace(client: TestClient) -> dict:
    cid = next(c["id"] for c in client.get("/churches").json() if c["name"] == GRACE)
    leaders = {x["name"]: x["person_id"] for x in client.get(f"/churches/{cid}/leaders").json()}
    people = {p["name"]: p["id"] for p in client.get(f"/churches/{cid}/people").json()}
    ministries = {m["name"]: m["id"] for m in client.get(f"/churches/{cid}/ministries").json()}
    return {"id": cid, "leaders": leaders, "people": people, "ministries": ministries}


def absences(client: TestClient, grace: dict, leader: str) -> list[dict]:
    path = f"/churches/{grace['id']}/leaders/{grace['leaders'][leader]}/briefing"
    response = client.get(path, params=DEMO_WEEK)
    assert response.status_code == 200, response.text
    return [i for i in response.json()["items"] if i["type"] == "absent"]


def answer(client: TestClient, grace: dict, finding_id: str, leader: str, choice: str) -> int:
    return client.post(
        f"/churches/{grace['id']}/findings/{finding_id}/answer",
        json={"person_id": grace["leaders"][leader], "answer": choice},
    ).status_code


def membership(session: Session, grace: dict) -> Membership:
    session.expire_all()
    return session.scalars(
        select(Membership).where(
            Membership.person_id == uuid.UUID(grace["people"]["Olivia Grant"]),
            Membership.ministry_id == uuid.UUID(grace["ministries"]["Kids"]),
        )
    ).one()


def test_the_approver_is_asked_about_someone_past_the_threshold(
    client: TestClient, grace: dict
) -> None:
    (item,) = absences(client, grace, "Sarah Collins")
    # Seven weeks before the demo Sunday, past Grace's six.
    assert item["text"] == "Olivia Grant hasn't served with Kids since 23 Aug."
    assert (item["severity"], item["people"], item["ministries"]) == (
        "noted",
        ["Olivia Grant"],
        ["Kids"],
    )
    # Asked once: reading the briefing again doesn't add a second one.
    assert [i["finding_id"] for i in absences(client, grace, "Sarah Collins")] == [
        item["finding_id"]
    ]
    # Only Kids' approver hears about it.
    assert absences(client, grace, "David Morales") == []


def test_yes_still_on_the_team_settles_it_and_changes_no_membership(
    client: TestClient, grace: dict, session: Session
) -> None:
    (item,) = absences(client, grace, "Sarah Collins")
    assert answer(client, grace, item["finding_id"], "David Morales", "still_here") == 403
    assert answer(client, grace, str(uuid.uuid4()), "Sarah Collins", "still_here") == 404
    audits = len(session.scalars(select(AuditLog)).all())

    assert answer(client, grace, item["finding_id"], "Sarah Collins", "still_here") == 204
    assert absences(client, grace, "Sarah Collins") == []  # not raised again
    olivia = membership(session, grace)
    assert olivia.status is MembershipStatus.ACTIVE and olivia.asked_at is None
    assert len(session.scalars(select(AuditLog)).all()) == audits  # the record didn't change


def test_ask_me_later_quiets_it_for_four_weeks(
    client: TestClient, grace: dict, session: Session
) -> None:
    (item,) = absences(client, grace, "Sarah Collins")
    assert answer(client, grace, item["finding_id"], "Sarah Collins", "later") == 204
    assert absences(client, grace, "Sarah Collins") == []
    olivia = membership(session, grace)
    assert olivia.status is MembershipStatus.ACTIVE and olivia.asked_at is not None
