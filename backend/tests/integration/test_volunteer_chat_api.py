"""The volunteer's side: approved reminders reach the demo chat, and replies are recorded
through proposals her own answer approves. Seeded demo week, today pinned to Thu 8 Oct 2026."""

import json
import uuid
from collections.abc import Iterator
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.api.ask import ask_llm_dependency, today_dependency
from app.channels.base import OutgoingMessage
from app.channels.simulator import SimulatorChannel
from app.db.models import (
    Assignment,
    AuditLog,
    Blockout,
    LeaderNotice,
    Message,
    Person,
    Proposal,
)
from app.domain.enums import AssignmentStatus, MessageStatus, ProposalStatus, StatedBy
from app.domain.replies import ParsedReply, ReplyIntent
from app.llm.fake import FakeLLM
from app.main import app
from tests.conftest import GRACE

TODAY = date(2026, 10, 8)


@pytest.fixture
def llm() -> Iterator[FakeLLM]:
    fake = FakeLLM()
    app.dependency_overrides[ask_llm_dependency] = lambda: fake
    yield fake
    app.dependency_overrides.pop(ask_llm_dependency, None)


@pytest.fixture
def grace(client: TestClient, llm: FakeLLM) -> Iterator[dict]:
    app.dependency_overrides[today_dependency] = lambda: TODAY
    cid = next(c["id"] for c in client.get("/churches").json() if c["name"] == GRACE)
    leaders = client.get(f"/churches/{cid}/leaders").json()
    ministries = {m["ministry"]: m["ministry_id"] for x in leaders for m in x["ministries"]}
    people = {p["name"]: p["id"] for p in client.get(f"/churches/{cid}/people").json()}
    yield {
        "id": cid,
        "leaders": {x["name"]: x["person_id"] for x in leaders},
        "kids": ministries["Kids"],
        "people": people,
    }
    app.dependency_overrides.pop(today_dependency, None)


def send_kids_reminders(client: TestClient, grace: dict) -> dict:
    """Draft (if not drafted yet) and approve Sunday's Kids reminders as Sarah."""
    client.post(f"/churches/{grace['id']}/ministries/{grace['kids']}/reminders/draft")
    pending = client.get(f"/churches/{grace['id']}/proposals", params={"status": "pending"})
    (proposal,) = [
        p
        for p in pending.json()
        if p["type"] == "reminders" and p["payload"]["ministry_id"] == grace["kids"]
    ]
    approved = client.post(
        f"/churches/{grace['id']}/proposals/{proposal['id']}/approve",
        json={"person_id": grace["leaders"]["Sarah Collins"]},
    )
    assert approved.status_code == 200, approved.text
    return proposal


def chat(client: TestClient, grace: dict, who: str):  # type: ignore[no-untyped-def]
    return client.get(f"/churches/{grace['id']}/people/{grace['people'][who]}/chat").json()


def say(client: TestClient, grace: dict, who: str, words: str) -> list[str]:
    response = client.post(
        f"/churches/{grace['id']}/people/{grace['people'][who]}/chat", json={"text": words}
    )
    assert response.status_code == 200, response.text
    return [r["body"] for r in response.json()["replies"]]


def annas_kids_place(session: Session, grace: dict) -> Assignment:
    return session.scalars(
        select(Assignment).where(
            Assignment.person_id == uuid.UUID(grace["people"]["Anna Parker"]),
            Assignment.ministry_id == uuid.UUID(grace["kids"]),
        )
    ).one()


def stored_anywhere(session: Session, words: str) -> list[str]:
    """Every table whose rows (as JSON text) contain the words."""
    tables = session.scalars(
        text("select tablename from pg_tables where schemaname = 'public'")
    ).all()
    return [
        t
        for t in tables
        if t != "alembic_version"
        and session.execute(
            text(f"select 1 from {t} x where row_to_json(x)::text ilike :w limit 1"),
            {"w": f"%{words}%"},
        ).first()
    ]


# --- sending ------------------------------------------------------------------


def test_only_approved_messages_reach_the_chat(
    client: TestClient, grace: dict, session: Session
) -> None:
    client.post(f"/churches/{grace['id']}/ministries/{grace['kids']}/reminders/draft")
    assert chat(client, grace, "Anna Parker")["messages"] == []  # drafted, not sent

    # A message that isn't approved is refused by the channel itself.
    anna = uuid.UUID(grace["people"]["Anna Parker"])
    draft = Message(
        church_id=uuid.UUID(grace["id"]), person_id=anna, channel="simulator", body="Hi"
    )
    session.add(draft)
    session.flush()
    assert draft.status is MessageStatus.DRAFT
    result = SimulatorChannel(session, uuid.UUID(grace["id"])).send(
        OutgoingMessage(draft.id, anna, "Anna Parker", None, "Hi")
    )
    assert result.ok is False
    assert chat(client, grace, "Anna Parker")["messages"] == []

    proposal = send_kids_reminders(client, grace)
    # Never the leader approving; everyone else on Sunday's Kids roster.
    assert {grace["people"][n] for n in ("Anna Parker", "Emily Brooks", "Rachel Turner")} <= {
        m["person_id"]
        for m in session.get_one(Proposal, uuid.UUID(proposal["id"])).payload["messages"]
    }
    (reminder,) = chat(client, grace, "Anna Parker")["messages"]
    assert reminder["approved"] is True
    assert reminder["body"] == (
        "Hi Anna! You're scheduled in Kids this Sunday, Oct 11, at 9:30, as Helper. "
        "Can you make it?"
    )
    assert reminder["buttons"] == ["Yes, I'll be there", "I can't make it"]


def test_one_persons_chat_is_never_shown_with_anothers(client: TestClient, grace: dict) -> None:
    send_kids_reminders(client, grace)
    say(client, grace, "Anna Parker", "1")
    rachel = chat(client, grace, "Rachel Turner")["messages"]
    assert [m["body"] for m in rachel] == [
        "Hi Rachel! You're scheduled in Kids this Sunday, Oct 11, at 9:30, as Helper. "
        "Can you make it?"
    ]
    assert all("Anna" not in m["body"] for m in rachel)


# --- answers ------------------------------------------------------------------


def test_yes_is_recorded_through_a_proposal_she_approves(
    client: TestClient, grace: dict, session: Session
) -> None:
    send_kids_reminders(client, grace)
    assert say(client, grace, "Anna Parker", "Yes, I'll be there") == [
        "Thank you, Anna! See you Sunday."
    ]
    assert annas_kids_place(session, grace).status is AssignmentStatus.CONFIRMED
    proposal = session.scalars(select(Proposal).where(Proposal.type == "reply_confirm")).one()
    assert proposal.status is ProposalStatus.APPROVED
    assert proposal.created_by_agent == "steward"
    assert str(proposal.decided_by_person_id) == grace["people"]["Anna Parker"]
    assert session.scalars(select(AuditLog).where(AuditLog.target_id == str(proposal.id))).one()
    # After an answer there's nothing left to answer, and no follow-up.
    assert say(client, grace, "Anna Parker", "1")[0].startswith("I can help with your serving")


def test_a_decline_with_a_personal_reason_is_passed_on_once_and_never_stored(
    client: TestClient, grace: dict, session: Session
) -> None:
    send_kids_reminders(client, grace)
    replies = say(client, grace, "Anna Parker", "2 — my mom is in the hospital.")
    assert replies == [
        "Thank you for letting me know. I've told your leader you can't make Oct 11."
    ]
    assert annas_kids_place(session, grace).status is AssignmentStatus.DECLINED
    # The reason lives only in the one-time notice for her leader.
    assert stored_anywhere(session, "mom is in the hospital") == ["leader_notices"]

    sarah = grace["leaders"]["Sarah Collins"]
    (notice,) = client.get(f"/churches/{grace['id']}/leaders/{sarah}/notices").json()
    assert notice["text"] == "Anna Parker can't make Sun Oct 11 (Kids, Helper)."
    assert notice["note"] == "2 — my mom is in the hospital."

    # Sarah's Home shows the gap, with someone free to fill it.
    brief = client.get(
        f"/churches/{grace['id']}/leaders/{sarah}/briefing", params={"start": TODAY.isoformat()}
    ).json()
    gap = next(i for i in brief["items"] if i["type"] == "below_minimum" and "Helper" in i["text"])
    assert gap["fill"] and gap["fill"]["name"] != "Anna Parker"
    # The double booking is gone with her Kids place.
    assert not any(i["type"] == "overlap" and "Anna Parker" in i["people"] for i in brief["items"])

    dismissed = client.delete(
        f"/churches/{grace['id']}/notices/{notice['id']}", params={"person_id": sarah}
    )
    assert dismissed.status_code == 204
    assert stored_anywhere(session, "mom is in the hospital") == []


def test_maybe_gets_one_question_and_is_never_recorded_as_yes(
    client: TestClient, grace: dict, session: Session
) -> None:
    send_kids_reminders(client, grace)
    (question,) = say(client, grace, "Anna Parker", "maybe, depends on work")
    assert question.startswith("No problem. Should I tell your leader you can't commit for Oct 11")
    assert chat(client, grace, "Anna Parker")["messages"][-1]["buttons"] == [
        "Can't commit",
        "I'll let you know",
    ]
    assert annas_kids_place(session, grace).status is AssignmentStatus.APPROVED

    # "1" here means "can't commit", never "yes".
    assert say(client, grace, "Anna Parker", "1") == [
        "Okay, I've let your leader know you can't commit for Oct 11."
    ]
    assert annas_kids_place(session, grace).status is AssignmentStatus.APPROVED
    assert not session.scalars(select(Proposal).where(Proposal.type == "reply_confirm")).all()
    kinds = [n.kind for n in session.scalars(select(LeaderNotice))]
    assert kinds == ["cant_commit"]


def test_away_dates_are_saved_only_after_she_confirms(
    client: TestClient, grace: dict, session: Session
) -> None:
    anna = uuid.UUID(grace["people"]["Anna Parker"])

    def away() -> list[date]:
        return list(
            session.scalars(
                select(Blockout.start_date).where(
                    Blockout.person_id == anna, Blockout.stated_by == StatedBy.VOLUNTEER
                )
            )
        )

    before = away()
    assert say(client, grace, "Anna Parker", "I'm out the 19th and the 26th.") == [
        "Got it: you're away Oct 19 and Oct 26. Is that right?"
    ]
    assert away() == before  # not yet
    assert say(client, grace, "Anna Parker", "2") == ["No problem. Which dates are you away?"]
    say(client, grace, "Anna Parker", "the 19th and the 26th")
    assert say(client, grace, "Anna Parker", "1") == [
        "Saved. You're away Oct 19 and Oct 26. Thank you!"
    ]
    assert sorted(set(away()) - set(before)) == [date(2026, 10, 19), date(2026, 10, 26)]


def test_stop_and_start(client: TestClient, grace: dict, session: Session) -> None:
    anna = session.get_one(Person, uuid.UUID(grace["people"]["Anna Parker"]))
    assert say(client, grace, "Anna Parker", "stop")[0].startswith(
        "Okay, I won't send you reminders anymore. I've let your leader know."
    )
    assert anna.stopped is True
    assert {n.kind for n in session.scalars(select(LeaderNotice))} == {"stopped"}

    # A stopped volunteer gets no reminders, even once a leader approves them.
    send_kids_reminders(client, grace)
    assert all(not m["approved"] for m in chat(client, grace, "Anna Parker")["messages"])

    assert say(client, grace, "Anna Parker", "start") == [
        "Welcome back! I'll send your reminders again."
    ]
    assert anna.stopped is False


def test_what_i_know_shows_only_what_she_told_shepherd(
    client: TestClient, grace: dict, session: Session
) -> None:
    (answer,) = say(client, grace, "Rachel Turner", "What do you remember about me?")
    assert answer.startswith("Here's what I have:\nTeams: Kids: Helper")
    # Leader memory about Rachel ("pair Emily with Rachel", "ready to lead a class") never shows.
    assert "pair" not in answer and "lead a class" not in answer
    assert "Veteran" not in answer and "New" not in answer  # experience is a leader's note too


def test_free_text_goes_to_the_model_and_code_decides(
    client: TestClient, grace: dict, session: Session, llm: FakeLLM
) -> None:
    send_kids_reminders(client, grace)
    llm.queue(ParsedReply(intent=ReplyIntent.DECLINE, dates=[]))
    replies = say(client, grace, "Anna Parker", "Unfortunately we have a family thing that day")
    assert replies[0].startswith("Thank you for letting me know.")
    assert annas_kids_place(session, grace).status is AssignmentStatus.DECLINED
    proposal = session.scalars(select(Proposal).where(Proposal.type == "reply_decline")).one()
    assert "family" not in json.dumps(proposal.payload)


def test_without_the_model_free_text_gets_the_numbered_fallback(
    client: TestClient, grace: dict
) -> None:
    app.dependency_overrides[ask_llm_dependency] = lambda: None
    send_kids_reminders(client, grace)
    assert say(client, grace, "Anna Parker", "hmm let me see about that") == [
        "Sorry, I didn't catch that. Reply 1 = yes, 2 = can't make it."
    ]


def test_a_tapped_button_sends_its_label_and_means_its_number(
    client: TestClient, grace: dict, session: Session
) -> None:
    send_kids_reminders(client, grace)
    say(client, grace, "Anna Parker", "not sure, it depends")
    assert say(client, grace, "Anna Parker", "Can't commit") == [
        "Okay, I've let your leader know you can't commit for Oct 11."
    ]
    assert annas_kids_place(session, grace).status is AssignmentStatus.APPROVED
