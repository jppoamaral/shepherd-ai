"""Schedule intake end to end with FakeLLM on Grace Community's Kids ministry (brief §11 intake)."""

import json
import uuid
from datetime import date

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.agents.steward import IntakeNotAllowed, IntakeUnreadable, StewardAgent
from app.db.models import Assignment, AuditLog, Membership, Person, Proposal, ScheduleIntake
from app.domain.enums import AssignmentSource, AssignmentStatus, IntakeStatus, QuestionKind, Weekday
from app.domain.intake import NicknameSuggestion, NicknameSuggestions, ParsedEntry, ParsedSchedule
from app.llm.fake import FakeLLM
from app.services.approval import ApprovalService
from app.services.errors import NotAllowed
from app.services.intake import LEAVE_OUT
from tests.conftest import SEED_TODAY

K = QuestionKind
PASTED = "KIDS OCT\n10/11 9:30 helpers: Rachel, Anna P. ... (Megan out - surgery)\n..."


def entry(
    names: list[str],
    *,
    day: str = "2026-10-25",  # the demo seed fills 10/11; keep these tests on clear dates
    at: str | None = "09:30",
    role: str = "Helper",
    both: bool = False,
) -> ParsedEntry:
    return ParsedEntry(
        date=day,
        weekday=Weekday.SUNDAY,
        time=at,
        gathering=None,
        all_gatherings_that_day=both,
        role_as_written=role,
        role=None,
        names=names,
    )


MESSY = ParsedSchedule(
    entries=[
        entry(["Rachel", "Anna P."]),
        entry(["Emily", "Annie"], at="11:00"),
        entry(["Megan"], role="chk-in"),
        entry(["Sarah"], day="2026-10-18", at=None, role="Lead Teacher", both=True),
    ],
    clarifying_question=None,
)
ANNIE = NicknameSuggestions(
    suggestions=[
        NicknameSuggestion(name_as_written="Annie", candidates=["Anna Peterson", "Not On Team"])
    ]
)


def person(session: Session, church_id: uuid.UUID, name: str) -> Person:
    found = session.scalar(select(Person).where(Person.church_id == church_id, Person.name == name))
    assert found is not None, name
    return found


@pytest.fixture
def kids_id(session: Session, grace_id: uuid.UUID) -> uuid.UUID:
    from app.db.models import Ministry

    mid = session.scalar(
        select(Ministry.id).where(Ministry.church_id == grace_id, Ministry.name == "Kids")
    )
    assert mid is not None
    return mid


@pytest.fixture
def llm() -> FakeLLM:
    return FakeLLM()


@pytest.fixture
def steward(session: Session, grace_id: uuid.UUID, llm: FakeLLM) -> StewardAgent:
    return StewardAgent(session, grace_id, llm, today=SEED_TODAY)


@pytest.fixture
def sarah(session: Session, grace_id: uuid.UUID) -> Person:
    return person(session, grace_id, "Sarah Collins")  # Kids scheduler and approver


def submit(steward: StewardAgent, llm: FakeLLM, kids_id: uuid.UUID, sarah: Person, parsed=MESSY):  # type: ignore[no-untyped-def]
    llm.queue(parsed)
    llm.queue(ANNIE)
    return steward.intake_schedule(kids_id, sarah.id, PASTED)


def kids_assignment_ids(session: Session, kids_id: uuid.UUID) -> set[uuid.UUID]:
    return set(session.scalars(select(Assignment.id).where(Assignment.ministry_id == kids_id)))


def choice_for(question, name: str) -> str:  # type: ignore[no-untyped-def]
    return next(c.id for c in question.choices if c.label.startswith(name))


def test_messy_schedule_becomes_slots_and_only_the_needed_questions(
    steward: StewardAgent, llm: FakeLLM, kids_id: uuid.UUID, sarah: Person
) -> None:
    view = submit(steward, llm, kids_id, sarah)
    assert view.status is IntakeStatus.NEEDS_ANSWERS
    kinds = {q.subject: q.kind for q in view.questions}
    assert kinds == {"Anna P.": K.AMBIGUOUS_NAME, "Annie": K.UNKNOWN_NAME, "chk-in": K.UNKNOWN_ROLE}
    # Rachel, Emily, Megan and Sarah matched; "both services" on 10/18 gave two Lead Teacher slots.
    assert "Rachel Turner" in view.summary and "Emily Brooks" in view.summary
    assert view.summary.count("Sarah Collins") == 2


def test_anna_p_is_asked_once_with_both_annas_and_never_merged(
    steward: StewardAgent, llm: FakeLLM, kids_id: uuid.UUID, sarah: Person
) -> None:
    view = submit(steward, llm, kids_id, sarah)
    (question,) = [q for q in view.questions if q.subject == "Anna P."]
    labels = [c.label for c in question.choices]
    assert labels == ["Anna Parker", "Anna Peterson", "Leave this out"]
    assert "Anna Parker" not in view.summary and "Anna Peterson" not in view.summary


def test_a_new_name_offers_only_real_team_suggestions(
    steward: StewardAgent, llm: FakeLLM, kids_id: uuid.UUID, sarah: Person
) -> None:
    view = submit(steward, llm, kids_id, sarah)
    (question,) = [q for q in view.questions if q.subject == "Annie"]
    assert "It might be Anna Peterson." in question.prompt  # "Not On Team" was dropped
    assert question.choices[0].label == "Anna Peterson (remember “Annie” for them)"
    assert question.choices[-1].id == LEAVE_OUT


def test_answering_everything_proposes_and_approval_records_the_roster(
    session: Session,
    grace_id: uuid.UUID,
    steward: StewardAgent,
    llm: FakeLLM,
    kids_id: uuid.UUID,
    sarah: Person,
) -> None:
    people_before = session.scalar(select(func.count()).select_from(Person))
    members_before = session.scalar(select(func.count()).select_from(Membership))
    seeded = kids_assignment_ids(session, kids_id)
    view = submit(steward, llm, kids_id, sarah)
    for question in list(view.questions):
        pick = {"Anna P.": "Anna Parker", "Annie": "Anna Peterson", "chk-in": "Check-in"}[
            question.subject
        ]
        view = steward.answer(view.id, sarah.id, question.id, choice_for(question, pick))

    assert view.status is IntakeStatus.PROPOSED and view.proposal_id is not None
    proposal = session.get_one(Proposal, view.proposal_id)
    assert (proposal.type, proposal.created_by_agent) == ("leader_roster", "steward")
    # Nothing is recorded before approval.
    assert kids_assignment_ids(session, kids_id) == seeded

    ApprovalService(session).approve(grace_id, proposal.id, sarah.id)

    rows = [
        a
        for a in session.scalars(select(Assignment).where(Assignment.ministry_id == kids_id))
        if a.id not in seeded
    ]
    assert len(rows) == 7  # Rachel, Anna Parker, Emily, Anna Peterson, Megan, Sarah x2
    assert {(r.status, r.source) for r in rows} == {
        (AssignmentStatus.APPROVED, AssignmentSource.LEADER)
    }
    assert "Annie" in person(session, grace_id, "Anna Peterson").nicknames
    assert session.get_one(ScheduleIntake, view.id).status is IntakeStatus.APPROVED

    entry_ = session.scalars(select(AuditLog).where(AuditLog.target_id == str(proposal.id))).one()
    assert (
        entry_.after
        and entry_.after["assignments_created"] == 7
        and entry_.after["nicknames_learned"] == 1
    )
    # Membership is an input: nothing was added (rule 6).
    assert session.scalar(select(func.count()).select_from(Person)) == people_before
    assert session.scalar(select(func.count()).select_from(Membership)) == members_before


def test_leaving_a_name_out_records_nothing_for_it(
    session: Session,
    grace_id: uuid.UUID,
    steward: StewardAgent,
    llm: FakeLLM,
    kids_id: uuid.UUID,
    sarah: Person,
) -> None:
    seeded = kids_assignment_ids(session, kids_id)
    llm.queue(ParsedSchedule(entries=[entry(["Rachel", "Jessie"])], clarifying_question=None))
    llm.queue(
        NicknameSuggestions(
            suggestions=[NicknameSuggestion(name_as_written="Jessie", candidates=[])]
        )
    )
    view = steward.intake_schedule(kids_id, sarah.id, "10/11 9:30 helpers Rachel, Jessie")
    (question,) = view.questions
    assert question.kind is K.UNKNOWN_NAME and "It might be" not in question.prompt
    view = steward.answer(view.id, sarah.id, question.id, LEAVE_OUT)
    assert view.proposal_id is not None
    ApprovalService(session).approve(grace_id, view.proposal_id, sarah.id)
    names = [
        session.get_one(Person, a.person_id).name
        for a in session.scalars(select(Assignment).where(Assignment.ministry_id == kids_id))
        if a.id not in seeded
    ]
    assert names == ["Rachel Turner"]


def test_someone_off_the_team_is_asked_about_not_assigned(
    steward: StewardAgent, llm: FakeLLM, kids_id: uuid.UUID, sarah: Person
) -> None:
    llm.queue(ParsedSchedule(entries=[entry(["Hannah"])], clarifying_question=None))
    view = steward.intake_schedule(kids_id, sarah.id, "10/11 9:30 helper Hannah")
    (question,) = view.questions
    assert question.kind is K.NOT_ON_TEAM
    assert "Hannah Wright isn't on the Kids team" in question.prompt


def test_a_clean_schedule_is_proposed_straight_away(
    steward: StewardAgent, llm: FakeLLM, kids_id: uuid.UUID, sarah: Person
) -> None:
    llm.queue(ParsedSchedule(entries=[entry(["Rachel", "Emily"])], clarifying_question=None))
    view = steward.intake_schedule(kids_id, sarah.id, "10/11 9:30 helpers Rachel, Emily")
    assert view.questions == [] and view.status is IntakeStatus.PROPOSED
    assert len(llm.calls) == 1  # no suggestion call when every name matched


def test_resubmitting_the_same_roster_skips_duplicates(
    session: Session,
    grace_id: uuid.UUID,
    steward: StewardAgent,
    llm: FakeLLM,
    kids_id: uuid.UUID,
    sarah: Person,
) -> None:
    for expected in (1, 0):
        llm.queue(ParsedSchedule(entries=[entry(["Rachel"])], clarifying_question=None))
        view = steward.intake_schedule(kids_id, sarah.id, "10/11 9:30 helper Rachel")
        assert view.proposal_id is not None
        ApprovalService(session).approve(grace_id, view.proposal_id, sarah.id)
        proposal = session.get_one(Proposal, view.proposal_id)
        entry_ = session.scalars(
            select(AuditLog).where(AuditLog.target_id == str(proposal.id))
        ).one()
        assert entry_.after and entry_.after["assignments_created"] == expected


def test_only_the_scheduler_submits_and_only_an_approver_approves(
    session: Session,
    grace_id: uuid.UUID,
    steward: StewardAgent,
    llm: FakeLLM,
    kids_id: uuid.UUID,
    sarah: Person,
) -> None:
    rachel = person(session, grace_id, "Rachel Turner")
    with pytest.raises(IntakeNotAllowed):
        steward.intake_schedule(kids_id, rachel.id, "anything")
    assert llm.calls == []  # refused before any model call

    llm.queue(ParsedSchedule(entries=[entry(["Emily"])], clarifying_question=None))
    view = steward.intake_schedule(kids_id, sarah.id, "10/11 9:30 helper Emily")
    assert view.proposal_id is not None
    with pytest.raises(NotAllowed):
        ApprovalService(session).approve(grace_id, view.proposal_id, rachel.id)


def test_unreadable_text_gets_a_question(
    steward: StewardAgent, llm: FakeLLM, kids_id: uuid.UUID, sarah: Person
) -> None:
    llm.queue(
        ParsedSchedule(entries=[], clarifying_question="Is this the Kids schedule for October?")
    )
    with pytest.raises(IntakeUnreadable, match="Kids schedule for October"):
        steward.intake_schedule(kids_id, sarah.id, "hello")


def test_pasted_text_is_never_stored(
    session: Session, steward: StewardAgent, llm: FakeLLM, kids_id: uuid.UUID, sarah: Person
) -> None:
    view = submit(steward, llm, kids_id, sarah)
    row = session.get_one(ScheduleIntake, view.id)
    assert "surgery" not in json.dumps(row.draft)
    assert not {"text", "raw", "pasted"} & set(ScheduleIntake.__table__.columns.keys())


def test_the_model_gets_today_roles_and_gatherings_as_facts(
    steward: StewardAgent, llm: FakeLLM, kids_id: uuid.UUID, sarah: Person
) -> None:
    submit(steward, llm, kids_id, sarah)
    parse_call, suggest_call = llm.calls
    assert '"today": "2026-10-08"' in parse_call["user"]
    assert (
        '"Check-in"' in parse_call["user"]
        and "Sunday 9:30 Service: Sun 2026-10-11 09:30" in parse_call["user"]
    )
    assert '"Annie"' in suggest_call["user"] and "Anna Peterson" in suggest_call["user"]
    assert date(2026, 10, 8) == SEED_TODAY
