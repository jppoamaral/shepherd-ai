"""Roster suggestion for a ministry: load the facts, draft, and approve an edited version.

Drafting is deterministic (`app.services.drafting`). Approving goes through a
`leader_roster` proposal and ApprovalService (rule 1), so it's recorded with
source=suggestion and lands in the audit log like any other approval.
"""

import uuid
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    Assignment,
    Blockout,
    Church,
    Gathering,
    GatheringType,
    LoadRule,
    Membership,
    Ministry,
    Person,
    Preference,
    PreferredGathering,
    Proposal,
    Role,
    RoleMinimum,
    RoleSkill,
)
from app.db.repositories.proposals import ProposalRepository
from app.domain.enums import AssignmentStatus, MembershipStatus, Period
from app.domain.schemas import (
    SuggestedAssignment,
    SuggestionAlternative,
    SuggestionLine,
    SuggestionOut,
)
from app.services.approval import ApprovalService
from app.services.drafting import Candidate, DraftFacts, Position, draft, period_start


def suggest(
    session: Session, church_id: uuid.UUID, ministry_id: uuid.UUID, start: date
) -> SuggestionOut | None:
    ministry = session.scalar(
        select(Ministry).where(Ministry.church_id == church_id, Ministry.id == ministry_id)
    )
    if ministry is None:
        return None
    church = session.get_one(Church, church_id)
    tz = ZoneInfo(church.timezone)
    end = start + timedelta(weeks=ministry.draft_horizon_weeks)
    window = (
        datetime.combine(start, time(0), tzinfo=tz),
        datetime.combine(end, time(0), tzinfo=tz),
    )

    roles = {
        r.id: r
        for r in session.scalars(
            select(Role).where(Role.church_id == church_id, Role.ministry_id == ministry_id)
        )
    }
    minimums = session.scalars(
        select(RoleMinimum).where(RoleMinimum.role_id.in_(roles), RoleMinimum.minimum > 0)
    ).all()
    by_type: dict[uuid.UUID, list[RoleMinimum]] = defaultdict(list)
    for m in minimums:
        by_type[m.gathering_type_id].append(m)

    gatherings = session.execute(
        select(Gathering, GatheringType.name)
        .join(GatheringType, GatheringType.id == Gathering.gathering_type_id)
        .where(
            Gathering.church_id == church_id,
            Gathering.start_at >= window[0],
            Gathering.start_at < window[1],
            Gathering.gathering_type_id.in_(by_type),
        )
        .order_by(Gathering.start_at)
    ).all()
    filled: dict[tuple[uuid.UUID, uuid.UUID], int] = defaultdict(int)
    for gathering_id, role_id in session.execute(
        select(Assignment.gathering_id, Assignment.role_id).where(
            Assignment.church_id == church_id,
            Assignment.ministry_id == ministry_id,
            Assignment.status != AssignmentStatus.DECLINED,
        )
    ):
        filled[(gathering_id, role_id)] += 1

    positions = [
        Position(
            g.id,
            g.gathering_type_id,
            name,
            g.start_at,
            g.end_at,
            g.start_at.astimezone(tz),
            m.role_id,
            roles[m.role_id].name,
        )
        for g, name in gatherings
        for m in by_type[g.gathering_type_id]
        for _ in range(max(0, m.minimum - filled[(g.id, m.role_id)]))
    ]
    lines = draft(
        positions,
        _facts(
            session,
            church_id,
            ministry_id,
            tz,
            start - timedelta(days=31),
            end + timedelta(days=31),
        ),
    )
    return SuggestionOut(
        ministry_id=ministry.id,
        ministry=ministry.name,
        start=start,
        end=end,
        lines=[
            SuggestionLine(
                gathering_id=line.position.gathering_id,
                gathering=line.position.gathering_name,
                start_at=line.position.local_start,
                role_id=line.position.role_id,
                role=line.position.role_name,
                person_id=line.person_id,
                name=line.name,
                experience=line.experience,
                reason=line.reason,
                flags=line.flags,
                alternatives=[
                    SuggestionAlternative(
                        person_id=a.person_id, name=a.name, experience=a.experience
                    )
                    for a in line.alternatives
                ],
            )
            for line in lines
        ],
        open=sum(1 for line in lines if line.person_id is None),
    )


def _facts(
    session: Session,
    church_id: uuid.UUID,
    ministry_id: uuid.UUID,
    tz: ZoneInfo,
    start: date,
    end: date,
) -> DraftFacts:
    team = session.execute(
        select(Person.id, Person.name, RoleSkill.role_id, RoleSkill.experience)
        .join(Membership, Membership.person_id == Person.id)
        .join(RoleSkill, RoleSkill.membership_id == Membership.id)
        .where(
            Membership.church_id == church_id,
            Membership.ministry_id == ministry_id,
            Membership.status == MembershipStatus.ACTIVE,
            Person.stopped.is_(False),
        )
    ).all()
    candidates: dict[uuid.UUID, Candidate] = {}
    for person_id, name, role_id, experience in team:
        candidates.setdefault(person_id, Candidate(person_id, name, {})).roles[role_id] = experience

    rule = session.scalars(
        select(LoadRule).where(LoadRule.church_id == church_id).order_by(LoadRule.period)
    ).first()
    period = rule.period if rule else Period.MONTH
    busy: dict[uuid.UUID, list[tuple[datetime, datetime]]] = defaultdict(list)
    served: dict[tuple[uuid.UUID, date], int] = defaultdict(int)
    for person_id, s, e in session.execute(
        select(Assignment.person_id, Gathering.start_at, Gathering.end_at)
        .join(Gathering, Gathering.id == Assignment.gathering_id)
        .where(
            Assignment.church_id == church_id,
            Assignment.status != AssignmentStatus.DECLINED,
            Gathering.start_at >= datetime.combine(start, time(0), tzinfo=tz),
            Gathering.start_at < datetime.combine(end, time(0), tzinfo=tz),
        )
    ):
        busy[person_id].append((s, e))
        served[(person_id, period_start(s.astimezone(tz).date(), period))] += 1

    blockouts: dict[uuid.UUID, list[tuple[date, date]]] = defaultdict(list)
    for b in session.scalars(select(Blockout).where(Blockout.church_id == church_id)):
        blockouts[b.person_id].append((b.start_date, b.end_date))
    preferred = {
        p.person_id: (p.preferred_frequency, p.preferred_frequency_period)
        for p in session.scalars(select(Preference).where(Preference.church_id == church_id))
        if p.preferred_frequency is not None and p.preferred_frequency_period is not None
    }
    gatherings_pref: dict[uuid.UUID, set[uuid.UUID]] = defaultdict(set)
    for pg in session.scalars(
        select(PreferredGathering).where(PreferredGathering.church_id == church_id)
    ):
        gatherings_pref[pg.person_id].add(pg.gathering_type_id)

    return DraftFacts(
        candidates=list(candidates.values()),
        busy=busy,
        blockouts=blockouts,
        served=served,
        period=period,
        usual=rule.normal_max if rule else None,
        preferred=preferred,
        preferred_gatherings=gatherings_pref,
    )


def approve_suggestion(
    session: Session,
    church_id: uuid.UUID,
    ministry_id: uuid.UUID,
    person_id: uuid.UUID,
    chosen: list[SuggestedAssignment],
) -> Proposal:
    """The leader approves their (possibly edited) roster: proposal, then ApprovalService."""
    proposal = ProposalRepository(session, church_id).create(
        type="leader_roster",
        payload={
            "ministry_id": str(ministry_id),
            "source": "suggestion",
            "assignments": [
                {
                    "gathering_id": str(a.gathering_id),
                    "role_id": str(a.role_id),
                    "person_id": str(a.person_id),
                    "reason": a.reason,
                }
                for a in chosen
            ],
            "nicknames": [],
        },
        created_by_agent="roster",
    )
    return ApprovalService(session).approve(church_id, proposal.id, person_id)
