"""ApprovalService and the church_profile handler: rules 1, 6 and 9 in practice."""

import uuid
from datetime import date
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import (
    AuditLog,
    Church,
    Gathering,
    GatheringType,
    LeaderAvailability,
    LoadRule,
    Membership,
    Ministry,
    MinistryLeader,
    OnboardingSession,
    Person,
    Proposal,
    RoleMinimum,
)
from app.db.repositories.proposals import ProposalRepository
from app.domain.enums import (
    GatheringKind,
    OnboardingStatus,
    ProfileStatus,
    ProposalStatus,
    Weekday,
)
from app.domain.profile import ChurchProfileDraft
from app.services import profile_apply
from app.services.approval import ApprovalService
from app.services.errors import ApprovalError, NotAllowed
from app.services.gatherings import ensure_gatherings
from app.services.onboarding import Started, start_onboarding
from tests.profile_script import SCRIPT, run


def propose(session: Session, started: Started, draft: ChurchProfileDraft) -> Proposal:
    proposal = ProposalRepository(session, started.church.id).create(
        type="church_profile", payload=draft.model_dump(mode="json"), created_by_agent="onboarding"
    )
    started.session.proposal_id = proposal.id
    started.session.status = OnboardingStatus.PROPOSED
    session.flush()
    return proposal


def count(session: Session, model: type, church_id: uuid.UUID) -> int:
    return (
        session.scalar(select(func.count()).select_from(model).where(model.church_id == church_id))
        or 0
    )


@pytest.fixture
def started(session: Session) -> Started:
    return start_onboarding(session, "Hope Chapel", "Pat Admin")


def test_a_new_church_starts_as_a_draft_that_runs_nothing(
    session: Session, started: Started
) -> None:
    church = session.get_one(Church, started.church.id)
    assert church.profile_status is ProfileStatus.DRAFT
    assert started.admin.is_admin
    assert ensure_gatherings(session, church.id, date(2026, 10, 1), date(2026, 12, 31)) == 0


def test_approving_applies_the_whole_profile(
    session: Session, started: Started, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(profile_apply, "local_today", lambda tz: date(2026, 10, 8))
    proposal = propose(session, started, run(SCRIPT))
    cid = started.church.id

    ApprovalService(session).approve(cid, proposal.id, started.admin.id)

    church = session.get_one(Church, cid)
    assert church.profile_status is ProfileStatus.APPROVED
    assert church.timezone == "America/Chicago"
    assert church.absence_threshold_weeks == 6
    assert church.warning_routing["overlap"] == ["scheduler", "approver"]
    assert (
        proposal.status is ProposalStatus.APPROVED
        and proposal.decided_by_person_id == started.admin.id
    )

    types = {
        t.name: t
        for t in session.scalars(select(GatheringType).where(GatheringType.church_id == cid))
    }
    assert types["Wednesday Prayer"].weekday is Weekday.WEDNESDAY
    assert types["Christmas Eve"].kind is GatheringKind.SPECIAL

    gatherings = session.scalars(select(Gathering).where(Gathering.church_id == cid)).all()
    weekdays = {
        g.start_at.astimezone(ZoneInfo("America/Chicago")).strftime("%A") for g in gatherings
    }
    assert {"Sunday", "Wednesday"} <= weekdays
    christmas = [g for g in gatherings if g.gathering_type_id == types["Christmas Eve"].id]
    assert len(christmas) == 1  # within the 12-week horizon from 2026-10-08

    assert {m.name for m in session.scalars(select(Ministry).where(Ministry.church_id == cid))} == {
        "Worship",
        "Kids",
    }
    assert count(session, RoleMinimum, cid) == 4
    assert count(session, MinistryLeader, cid) == 2
    assert count(session, LoadRule, cid) == 1
    assert count(session, LeaderAvailability, cid) == 1
    kids = session.scalar(
        select(Ministry).where(Ministry.church_id == cid, Ministry.name == "Kids")
    )
    assert kids is not None and (kids.show_both_paths, kids.draft_horizon_weeks) == (False, 6)

    # Leaders become people; nobody is put on a team (rule 6).
    names = set(session.scalars(select(Person.name).where(Person.church_id == cid)))
    assert names == {"Pat Admin", "David Morales", "Sarah Collins"}
    assert count(session, Membership, cid) == 0

    onboarding = session.get_one(OnboardingSession, started.session.id)
    assert onboarding.status is OnboardingStatus.APPROVED

    (entry,) = session.scalars(select(AuditLog).where(AuditLog.church_id == cid)).all()
    assert entry.action == "proposal.approved"
    assert entry.approved_by_person_id == started.admin.id
    assert entry.target_id == str(proposal.id)
    assert entry.after and entry.after["ministries"] == 2


def test_rejecting_applies_nothing_but_is_logged(session: Session, started: Started) -> None:
    proposal = propose(session, started, run(SCRIPT))
    cid = started.church.id

    ApprovalService(session).reject(cid, proposal.id, started.admin.id)

    assert session.get_one(Church, cid).profile_status is ProfileStatus.DRAFT
    assert count(session, Ministry, cid) == 0 and count(session, GatheringType, cid) == 0
    assert proposal.status is ProposalStatus.REJECTED
    onboarding = session.get_one(OnboardingSession, started.session.id)
    assert (onboarding.status, onboarding.proposal_id) == (OnboardingStatus.ACTIVE, None)
    (entry,) = session.scalars(select(AuditLog).where(AuditLog.church_id == cid)).all()
    assert entry.action == "proposal.rejected" and entry.approved_by_person_id is None


def test_a_proposal_is_decided_only_once(session: Session, started: Started) -> None:
    proposal = propose(session, started, run(SCRIPT))
    service = ApprovalService(session)
    service.approve(started.church.id, proposal.id, started.admin.id)
    with pytest.raises(ApprovalError, match="already approved"):
        service.approve(started.church.id, proposal.id, started.admin.id)
    with pytest.raises(ApprovalError, match="already approved"):
        service.reject(started.church.id, proposal.id, started.admin.id)


def test_only_an_admin_of_that_church_may_decide(
    session: Session, started: Started, grace_id: uuid.UUID
) -> None:
    proposal = propose(session, started, run(SCRIPT))
    volunteer = Person(church_id=started.church.id, name="Not An Admin")
    session.add(volunteer)
    session.flush()
    with pytest.raises(NotAllowed):
        ApprovalService(session).approve(started.church.id, proposal.id, volunteer.id)

    # An admin of another church can't even see the proposal.
    with pytest.raises(ApprovalError, match="not found"):
        ApprovalService(session).approve(grace_id, proposal.id, started.admin.id)
    assert proposal.status is ProposalStatus.PENDING


def test_an_incomplete_profile_is_refused_even_if_proposed(
    session: Session, started: Started
) -> None:
    proposal = propose(session, started, run(SCRIPT[:3]))
    with pytest.raises(ApprovalError, match="isn't complete"):
        ApprovalService(session).approve(started.church.id, proposal.id, started.admin.id)
