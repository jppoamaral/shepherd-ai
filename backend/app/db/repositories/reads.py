"""Read-only, church-scoped queries. Safe for agents, services and the API.

Every method filters by the `church_id` the repository was built with
(architecture rule 3); there is no unscoped query here.
"""

import uuid
from collections import defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    Church,
    Gathering,
    GatheringType,
    LoadRule,
    Membership,
    Ministry,
    MinistryLeader,
    Person,
    Proposal,
    Role,
    RoleMinimum,
    RoleSkill,
)
from app.domain.enums import ProposalStatus
from app.domain.schemas import (
    ChurchOut,
    GatheringOut,
    GatheringTypeOut,
    LeaderOut,
    LoadRuleOut,
    MembershipOut,
    MinistryOut,
    PersonOut,
    ProposalOut,
    RoleMinimumOut,
    RoleOut,
    RoleSkillOut,
)


def list_churches(session: Session) -> list[ChurchOut]:
    """The tenant directory itself; the only cross-church read."""
    churches = session.scalars(select(Church).order_by(Church.name)).all()
    return [ChurchReader(session, c.id).church() for c in churches]


class ChurchReader:
    def __init__(self, session: Session, church_id: uuid.UUID) -> None:
        self.session = session
        self.church_id = church_id

    def church(self) -> ChurchOut:
        church = self.session.get_one(Church, self.church_id)
        rules = self.session.scalars(
            select(LoadRule).where(LoadRule.church_id == self.church_id).order_by(LoadRule.period)
        ).all()
        return ChurchOut(
            id=church.id,
            name=church.name,
            timezone=church.timezone,
            language=church.language,
            profile_status=church.profile_status,
            member_count=church.member_count,
            load_rules=[LoadRuleOut.model_validate(r) for r in rules],
        )

    def gathering_types(self) -> list[GatheringTypeOut]:
        types = self.session.scalars(
            select(GatheringType)
            .where(GatheringType.church_id == self.church_id)
            .order_by(GatheringType.name)
        ).all()
        return [GatheringTypeOut.model_validate(t) for t in types]

    def ministries(self) -> list[MinistryOut]:
        cid = self.church_id
        ministries = self.session.scalars(
            select(Ministry).where(Ministry.church_id == cid).order_by(Ministry.name)
        ).all()
        roles = self.session.scalars(
            select(Role).where(Role.church_id == cid).order_by(Role.name)
        ).all()
        minimums = self.session.scalars(select(RoleMinimum).where(RoleMinimum.church_id == cid))
        leaders = self.session.execute(
            select(MinistryLeader, Person.name)
            .join(Person, Person.id == MinistryLeader.person_id)
            .where(MinistryLeader.church_id == cid, Person.church_id == cid)
            .order_by(Person.name)
        ).all()

        minimums_by_role: dict[uuid.UUID, list[RoleMinimumOut]] = defaultdict(list)
        for m in minimums:
            minimums_by_role[m.role_id].append(RoleMinimumOut.model_validate(m))
        roles_by_ministry: dict[uuid.UUID, list[RoleOut]] = defaultdict(list)
        for r in roles:
            roles_by_ministry[r.ministry_id].append(
                RoleOut(id=r.id, name=r.name, minimums=minimums_by_role[r.id])
            )
        leaders_by_ministry: dict[uuid.UUID, list[LeaderOut]] = defaultdict(list)
        for leader, name in leaders:
            leaders_by_ministry[leader.ministry_id].append(
                LeaderOut(
                    person_id=leader.person_id,
                    name=name,
                    can_schedule=leader.can_schedule,
                    can_approve=leader.can_approve,
                )
            )
        return [
            MinistryOut(
                id=m.id,
                name=m.name,
                aliases=m.aliases,
                show_both_paths=m.show_both_paths,
                default_path=m.default_path,
                draft_horizon_weeks=m.draft_horizon_weeks,
                roles=roles_by_ministry[m.id],
                leaders=leaders_by_ministry[m.id],
            )
            for m in ministries
        ]

    def people(self) -> list[PersonOut]:
        cid = self.church_id
        people = self.session.scalars(
            select(Person).where(Person.church_id == cid).order_by(Person.name)
        ).all()
        memberships = self.session.execute(
            select(Membership, Ministry.name)
            .join(Ministry, Ministry.id == Membership.ministry_id)
            .where(Membership.church_id == cid, Ministry.church_id == cid)
            .order_by(Ministry.name)
        ).all()
        skills = self.session.execute(
            select(RoleSkill, Role.name)
            .join(Role, Role.id == RoleSkill.role_id)
            .where(RoleSkill.church_id == cid, Role.church_id == cid)
            .order_by(Role.name)
        ).all()

        skills_by_membership: dict[uuid.UUID, list[RoleSkillOut]] = defaultdict(list)
        for skill, role_name in skills:
            skills_by_membership[skill.membership_id].append(
                RoleSkillOut(role_id=skill.role_id, role=role_name, experience=skill.experience)
            )
        memberships_by_person: dict[uuid.UUID, list[MembershipOut]] = defaultdict(list)
        for membership, ministry_name in memberships:
            memberships_by_person[membership.person_id].append(
                MembershipOut(
                    ministry_id=membership.ministry_id,
                    ministry=ministry_name,
                    status=membership.status,
                    last_served=membership.last_served,
                    roles=skills_by_membership[membership.id],
                )
            )
        return [
            PersonOut(
                id=p.id,
                name=p.name,
                nicknames=p.nicknames,
                opted_in=p.opted_in,
                stopped=p.stopped,
                memberships=memberships_by_person[p.id],
            )
            for p in people
        ]

    def proposals(self, status: ProposalStatus | None = None) -> list[ProposalOut]:
        query = select(Proposal).where(Proposal.church_id == self.church_id)
        if status is not None:
            query = query.where(Proposal.status == status)
        rows = self.session.scalars(query.order_by(Proposal.created_at.desc())).all()
        return [ProposalOut.model_validate(p) for p in rows]

    def gatherings(self, start: datetime, end: datetime) -> list[GatheringOut]:
        """Gatherings starting in `[start, end)`, with times in the church's time zone."""
        tz = ZoneInfo(self.session.get_one(Church, self.church_id).timezone)
        rows = self.session.execute(
            select(Gathering, GatheringType)
            .join(GatheringType, GatheringType.id == Gathering.gathering_type_id)
            .where(
                Gathering.church_id == self.church_id,
                GatheringType.church_id == self.church_id,
                Gathering.start_at >= start,
                Gathering.start_at < end,
            )
            .order_by(Gathering.start_at)
        ).all()
        return [
            GatheringOut(
                id=g.id,
                gathering_type_id=t.id,
                name=t.name,
                kind=t.kind,
                start_at=g.start_at.astimezone(tz),
                end_at=g.end_at.astimezone(tz),
            )
            for g, t in rows
        ]
