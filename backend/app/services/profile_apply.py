"""Applies an approved `church_profile` proposal. Called only by ApprovalService.

Writes the church's onboarding profile: gathering types, ministries, roles and
minimums, leaders and their availability, load rules, routing and settings. It
creates Person rows for leaders only; it never creates memberships (rule 6).
"""

from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import (
    Church,
    GatheringType,
    LeaderAvailability,
    LoadRule,
    Ministry,
    MinistryLeader,
    OnboardingSession,
    Person,
    Proposal,
    Role,
    RoleMinimum,
)
from app.domain.enums import OnboardingStatus, ProfileStatus
from app.domain.profile import ChurchProfileDraft
from app.services.errors import ApprovalError
from app.services.gatherings import ensure_gatherings
from app.services.profile import proposal_blockers

PROPOSAL_TYPE = "church_profile"


def may_decide(session: Session, proposal: Proposal, person: Person) -> bool:
    return person.is_admin and person.church_id == proposal.church_id


def apply(session: Session, proposal: Proposal, approver: Person) -> dict[str, Any]:
    church = session.get_one(Church, proposal.church_id)
    if church.profile_status is not ProfileStatus.DRAFT:
        raise ApprovalError("this church's profile is already approved")
    draft = ChurchProfileDraft.model_validate(proposal.payload)
    if blockers := proposal_blockers(draft):
        raise ApprovalError("the profile isn't complete: " + " ".join(blockers))
    assert draft.timezone is not None
    cid = church.id

    church.timezone = draft.timezone
    church.language = draft.language
    church.absence_threshold_weeks = draft.absence_threshold_weeks
    church.warning_routing = {
        r.finding.value: [x.value for x in r.recipients] for r in draft.routing
    }

    for rule in draft.load_rules:
        session.add(
            LoadRule(
                church_id=cid,
                period=rule.period,
                normal_max=rule.normal_max,
                warning_above=rule.warning_above,
            )
        )

    gathering_types = {
        g.name: GatheringType(
            church_id=cid,
            name=g.name,
            kind=g.kind,
            recurrence=g.recurrence,
            weekday=g.weekday,
            one_off_date=g.one_off_date,
            local_start_time=g.local_start_time,
            duration_minutes=g.duration_minutes,
        )
        for g in draft.gatherings
    }
    session.add_all(gathering_types.values())

    people = {
        p.name.casefold(): p for p in session.scalars(select(Person).where(Person.church_id == cid))
    }

    def person_named(name: str) -> Person:
        if (found := people.get(name.casefold())) is None:
            found = people[name.casefold()] = Person(church_id=cid, name=name)
            session.add(found)
        return found

    leader_count = 0
    for m in draft.ministries:
        ministry = Ministry(
            church_id=cid,
            name=m.name,
            aliases=m.aliases,
            show_both_paths=m.show_both_paths,
            default_path=m.default_path,
            draft_horizon_weeks=m.draft_horizon_weeks,
        )
        session.add(ministry)
        session.flush()
        for r in m.roles:
            role = Role(church_id=cid, ministry_id=ministry.id, name=r.name)
            session.add(role)
            session.flush()
            for minimum in r.minimums:
                session.add(
                    RoleMinimum(
                        church_id=cid,
                        role_id=role.id,
                        gathering_type_id=gathering_types[minimum.gathering].id,
                        minimum=minimum.minimum,
                    )
                )
        for leader in m.leaders:
            person = person_named(leader.name)
            session.flush()
            session.add(
                MinistryLeader(
                    church_id=cid,
                    ministry_id=ministry.id,
                    person_id=person.id,
                    can_schedule=leader.can_schedule,
                    can_approve=leader.can_approve,
                )
            )
            leader_count += 1

    for window in draft.availability:
        session.add(
            LeaderAvailability(
                church_id=cid,
                person_id=person_named(window.leader).id,
                weekday=window.weekday,
                start_time=window.start,
                end_time=window.end,
            )
        )

    church.profile_status = ProfileStatus.APPROVED
    session.flush()

    today = local_today(church.timezone)
    horizon = timedelta(weeks=get_settings().gathering_horizon_weeks)
    created = ensure_gatherings(session, cid, today, today + horizon)

    for onboarding in session.scalars(
        select(OnboardingSession).where(
            OnboardingSession.church_id == cid, OnboardingSession.proposal_id == proposal.id
        )
    ):
        onboarding.status = OnboardingStatus.APPROVED

    return {
        "gathering_types": len(gathering_types),
        "ministries": len(draft.ministries),
        "leaders": leader_count,
        "load_rules": len(draft.load_rules),
        "gatherings_created": created,
    }


def local_today(timezone: str) -> date:
    """The church's current date (a seam tests can replace)."""
    return datetime.now(ZoneInfo(timezone)).date()


def on_reject(session: Session, proposal: Proposal) -> None:
    """Send the admin back to review so they can change the draft and propose again."""
    for onboarding in session.scalars(
        select(OnboardingSession).where(
            OnboardingSession.church_id == proposal.church_id,
            OnboardingSession.proposal_id == proposal.id,
        )
    ):
        onboarding.status = OnboardingStatus.ACTIVE
        onboarding.proposal_id = None
