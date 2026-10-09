"""Conflict huddle over HTTP on the seeded demo week (clock pinned to Thu 8 Oct 6 PM)."""

import uuid
from collections.abc import Iterator
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.huddles import now_dependency
from app.db.models import Assignment, AuditLog, Blockout, Huddle, Message, Proposal
from app.domain.enums import ProposalStatus, StatedBy
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


# --- Resolve: the Kids leader accepts Shepherd's replacement on her own roster ------------


def kids_huddle(client: TestClient, grace: dict) -> tuple[dict, dict, str]:
    """Sarah's huddle over Anna's double booking, its Kids side, and the endpoint base."""
    finding = overlap_for(client, grace, "Sarah Collins", "Anna Parker")
    huddle = start(client, grace, finding, "Sarah Collins").json()
    kids = next(s for s in huddle["agenda"]["sides"] if s["ministry"] == "Kids")
    return huddle, kids, f"/churches/{grace['id']}/huddles/{huddle['id']}"


def resolve_kids(
    client: TestClient, grace: dict, base: str, kids: dict, leader: str = "Sarah Collins"
):  # type: ignore[no-untyped-def]
    return client.post(
        f"{base}/accept-replacement",
        json={"person_id": grace["leaders"][leader], "ministry_id": kids["ministry_id"]},
    )


def counts(session: Session, grace: dict) -> tuple[int, int]:
    church = uuid.UUID(grace["id"])
    messages = session.scalar(select(func.count()).where(Message.church_id == church))
    proposals = session.scalar(select(func.count()).where(Proposal.church_id == church))
    return messages or 0, proposals or 0


def test_resolve_puts_the_replacement_in_annas_kids_place_once(
    client: TestClient, grace: dict, session: Session
) -> None:
    _, kids, base = kids_huddle(client, grace)
    assert kids["replacement_person_id"] and kids["ministry_id"]
    anna = uuid.UUID(grace["people"]["Anna Parker"])
    anna_before = session.scalar(select(func.count()).where(Assignment.person_id == anna))

    response = resolve_kids(client, grace, base, kids)
    assert response.status_code == 200, response.text
    out = response.json()
    assert out["status"] == "resolved"
    assert out["finding_status"] == "resolved"  # the double booking is gone
    assert out["replacement"] == {
        "ministry_id": kids["ministry_id"],
        "ministry": "Kids",
        "resolved_by": "Sarah Collins",
        "volunteer": "Anna Parker",
        "replacement": kids["replacement"],
        "can_undo": True,
    }
    row = session.scalars(
        select(Assignment).where(Assignment.reason.like("%settled from the huddle%"))
    ).one()
    assert row.person_id == uuid.UUID(kids["replacement_person_id"])
    # Anna keeps her Worship place; only her Kids place moved.
    assert session.scalar(select(func.count()).where(Assignment.person_id == anna)) == (
        anna_before - 1
    )
    approved = session.scalars(
        select(Proposal).where(Proposal.type == "huddle_accept_replacement")
    ).all()
    assert [p.status for p in approved] == [ProposalStatus.APPROVED]

    again = resolve_kids(client, grace, base, kids)
    assert again.status_code == 409
    assert (
        session.scalar(select(func.count()).where(Proposal.type == "huddle_accept_replacement"))
        == 1
    )
    assert session.get_one(Assignment, row.id).person_id == uuid.UUID(kids["replacement_person_id"])


def test_resolve_writes_an_audit_entry(client: TestClient, grace: dict, session: Session) -> None:
    _, kids, base = kids_huddle(client, grace)
    assert resolve_kids(client, grace, base, kids).status_code == 200
    proposal = session.scalars(
        select(Proposal).where(Proposal.type == "huddle_accept_replacement")
    ).one()
    entry = session.scalars(select(AuditLog).where(AuditLog.target_id == str(proposal.id))).one()
    assert entry.action == "proposal.approved"
    assert entry.target_type == "proposal:huddle_accept_replacement"
    assert entry.actor == f"person:{grace['leaders']['Sarah Collins']}"
    assert entry.approved_by_person_id == uuid.UUID(grace["leaders"]["Sarah Collins"])
    assert entry.after is not None
    assert entry.after["from_person_id"] == grace["people"]["Anna Parker"]
    assert entry.after["to_person_id"] == kids["replacement_person_id"]


def test_resolve_notifies_no_one(client: TestClient, grace: dict, session: Session) -> None:
    _, kids, base = kids_huddle(client, grace)
    messages_before, _ = counts(session, grace)
    assert resolve_kids(client, grace, base, kids).status_code == 200
    messages_after, _ = counts(session, grace)
    assert messages_after == messages_before
    for person in (grace["leaders"]["David Morales"], grace["people"]["Anna Parker"]):
        assert not session.scalars(
            select(Message).where(Message.person_id == uuid.UUID(person))
        ).all()


def test_resolve_does_nothing_once_the_conflict_is_settled(
    client: TestClient, grace: dict, session: Session
) -> None:
    _, kids, base = kids_huddle(client, grace)
    recorded = client.post(
        f"{base}/resolve",
        json={"person_id": grace["leaders"]["Sarah Collins"], "outcome": "Anna stays on keys."},
    )
    assert recorded.status_code == 200
    _, proposals_before = counts(session, grace)

    response = resolve_kids(client, grace, base, kids)
    assert response.status_code == 409
    assert counts(session, grace)[1] == proposals_before  # no proposal left behind
    assert not session.scalars(
        select(Assignment).where(Assignment.reason.like("%settled from the huddle%"))
    ).all()


def test_resolve_does_nothing_when_the_replacement_no_longer_fits(
    client: TestClient, grace: dict, session: Session
) -> None:
    _, kids, base = kids_huddle(client, grace)
    # The suggested helper becomes unavailable after the huddle was offered.
    session.add(
        Blockout(
            church_id=uuid.UUID(grace["id"]),
            person_id=uuid.UUID(kids["replacement_person_id"]),
            start_date=date(2026, 10, 10),
            end_date=date(2026, 10, 12),
            stated_by=StatedBy.VOLUNTEER,
        )
    )
    session.flush()
    _, proposals_before = counts(session, grace)

    response = resolve_kids(client, grace, base, kids)
    assert response.status_code == 409
    assert "can't take Anna's place" in response.json()["detail"]
    assert counts(session, grace)[1] == proposals_before
    assert not session.scalars(
        select(Assignment).where(Assignment.reason.like("%settled from the huddle%"))
    ).all()
    huddle = client.get(base).json()
    assert huddle["status"] == "offered" and huddle["finding_status"] == "open"


def test_only_the_kids_approver_can_resolve_the_kids_side(
    client: TestClient, grace: dict, session: Session
) -> None:
    _, kids, base = kids_huddle(client, grace)
    _, proposals_before = counts(session, grace)
    response = resolve_kids(client, grace, base, kids, leader="David Morales")
    assert response.status_code == 403
    assert counts(session, grace)[1] == proposals_before


def test_undo_puts_anna_back_and_reopens_the_conflict(
    client: TestClient, grace: dict, session: Session
) -> None:
    _, kids, base = kids_huddle(client, grace)
    assert resolve_kids(client, grace, base, kids).status_code == 200
    sarah = grace["leaders"]["Sarah Collins"]

    undone = client.post(f"{base}/undo-replacement", json={"person_id": sarah})
    assert undone.status_code == 200, undone.text
    out = undone.json()
    assert out["status"] == "offered" and out["replacement"] is None and out["outcome"] is None
    assert out["finding_status"] == "open"
    assert not session.scalars(
        select(Assignment).where(Assignment.reason.like("%settled from the huddle%"))
    ).all()
    undo = session.scalars(select(Proposal).where(Proposal.type == "huddle_undo_replacement")).one()
    assert session.scalars(select(AuditLog).where(AuditLog.target_id == str(undo.id))).one()

    assert client.post(f"{base}/undo-replacement", json={"person_id": sarah}).status_code == 409


def test_a_huddle_saved_before_resolve_existed_gets_its_ids_when_reopened(
    client: TestClient, grace: dict, session: Session
) -> None:
    huddle, kids, _ = kids_huddle(client, grace)
    row = session.get_one(Huddle, uuid.UUID(huddle["id"]))
    agenda = dict(row.details["agenda"])
    agenda["sides"] = [
        {k: v for k, v in side.items() if k not in ("ministry_id", "replacement_person_id")}
        for side in agenda["sides"]
    ]
    row.details = {**row.details, "agenda": agenda}
    session.flush()

    finding = overlap_for(client, grace, "Sarah Collins", "Anna Parker")
    reopened = start(client, grace, finding, "Sarah Collins").json()
    again = next(s for s in reopened["agenda"]["sides"] if s["ministry"] == "Kids")
    assert again["ministry_id"] == kids["ministry_id"]
    assert again["replacement_person_id"] == kids["replacement_person_id"]
