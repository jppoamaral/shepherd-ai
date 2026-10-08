"""Write a ChurchSeed to the database. Re-running is safe.

Seeds are fixtures: they stand in for an approved onboarding profile and an
already-approved roster history, so they write the record directly rather than
going through proposals. Each load is recorded in the audit log as actor "seed".
"""

import uuid
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    Blockout,
    Church,
    Gathering,
    GatheringType,
    LeaderAvailability,
    LoadRule,
    Membership,
    Ministry,
    MinistryLeader,
    Person,
    Preference,
    PreferredGathering,
    Role,
    RoleMinimum,
    RoleSkill,
)
from app.db.repositories.assignments import AssignmentWriter
from app.db.repositories.audit import AuditLogRepository
from app.domain.enums import (
    AssignmentSource,
    AssignmentStatus,
    ProfileStatus,
    Recurrence,
    StatedBy,
)
from app.services.gatherings import ensure_gatherings
from seeds.generate import generate_volunteers
from seeds.spec import ChurchSeed

GATHERING_HORIZON_WEEKS = 16


def load_church(session: Session, spec: ChurchSeed, today: date) -> tuple[Church, bool]:
    """Create the church if it doesn't exist, then extend its gatherings.

    Returns `(church, created)`. An existing church is left as is apart from new
    gatherings, so re-running the seed never duplicates rows.
    """
    existing = session.scalar(select(Church).where(Church.name == spec.name))
    if existing is not None:
        ensure_gatherings(
            session, existing.id, today, today + timedelta(weeks=GATHERING_HORIZON_WEEKS)
        )
        return existing, False

    church = Church(
        name=spec.name,
        timezone=spec.timezone,
        language="en",
        profile_status=ProfileStatus.APPROVED,
        member_count=spec.member_count,
        absence_threshold_weeks=spec.absence_threshold_weeks,
        warning_routing=spec.warning_routing,
    )
    session.add(church)
    session.flush()
    cid = church.id

    for period, normal_max, warning_above in spec.load_rules:
        session.add(
            LoadRule(
                church_id=cid, period=period, normal_max=normal_max, warning_above=warning_above
            )
        )

    gathering_types: dict[str, GatheringType] = {}
    for g in spec.gathering_types:
        gathering_types[g.key] = GatheringType(
            church_id=cid,
            name=g.name,
            kind=g.kind,
            recurrence=Recurrence.WEEKLY if g.weekday else Recurrence.ONE_OFF,
            weekday=g.weekday,
            one_off_date=g.one_off_date,
            local_start_time=g.local_start_time,
            duration_minutes=g.duration_minutes,
        )
    session.add_all(gathering_types.values())

    people_specs = [*spec.people, *generate_volunteers(spec)]
    people = {
        p.key: Person(church_id=cid, name=p.name, nicknames=p.nicknames, opted_in=p.opted_in)
        for p in people_specs
    }
    session.add_all(people.values())

    ministries: dict[str, Ministry] = {}
    roles: dict[tuple[str, str], Role] = {}
    scheduler_of: dict[str, uuid.UUID] = {}
    for m in spec.ministries:
        ministry = Ministry(
            church_id=cid,
            name=m.name,
            aliases=m.aliases,
            draft_horizon_weeks=m.draft_horizon_weeks,
        )
        ministries[m.name] = ministry
        session.add(ministry)
        session.flush()
        for r in m.roles:
            role = Role(church_id=cid, ministry_id=ministry.id, name=r.name)
            roles[(m.name, r.name)] = role
            session.add(role)
        session.flush()
        for r in m.roles:
            for gt_key, minimum in r.minimums.items():
                session.add(
                    RoleMinimum(
                        church_id=cid,
                        role_id=roles[(m.name, r.name)].id,
                        gathering_type_id=gathering_types[gt_key].id,
                        minimum=minimum,
                    )
                )
        for leader in m.leaders:
            session.add(
                MinistryLeader(
                    church_id=cid,
                    ministry_id=ministry.id,
                    person_id=people[leader.person].id,
                    can_schedule=leader.can_schedule,
                    can_approve=leader.can_approve,
                )
            )
        scheduler_of[m.name] = people[next(lr.person for lr in m.leaders if lr.can_schedule)].id
    session.flush()

    joined = today - timedelta(weeks=26)
    for p in people_specs:
        person = people[p.key]
        for ministry_name, skills in p.skills.items():
            membership = Membership(
                church_id=cid,
                person_id=person.id,
                ministry_id=ministries[ministry_name].id,
                status_since=joined,
            )
            session.add(membership)
            session.flush()
            for role_name, experience in skills.items():
                session.add(
                    RoleSkill(
                        church_id=cid,
                        membership_id=membership.id,
                        role_id=roles[(ministry_name, role_name)].id,
                        experience=experience,
                        set_by_person_id=scheduler_of[ministry_name],
                    )
                )
        if p.preferred_frequency is not None:
            count, period = p.preferred_frequency
            session.add(
                Preference(
                    church_id=cid,
                    person_id=person.id,
                    preferred_frequency=count,
                    preferred_frequency_period=period,
                    stated_by=StatedBy.VOLUNTEER,
                )
            )
        for gt_key in p.preferred_gatherings:
            session.add(
                PreferredGathering(
                    church_id=cid,
                    person_id=person.id,
                    gathering_type_id=gathering_types[gt_key].id,
                    stated_by=StatedBy.VOLUNTEER,
                )
            )
        for b in p.blockouts:
            session.add(
                Blockout(
                    church_id=cid,
                    person_id=person.id,
                    start_date=today + timedelta(days=b.start_offset_days),
                    end_date=today + timedelta(days=b.end_offset_days),
                    stated_by=StatedBy.VOLUNTEER,
                )
            )
        for window in p.availability:
            session.add(
                LeaderAvailability(
                    church_id=cid,
                    person_id=person.id,
                    weekday=window.weekday,
                    start_time=window.start,
                    end_time=window.end,
                )
            )
    session.flush()

    ensure_gatherings(session, cid, today, today + timedelta(weeks=GATHERING_HORIZON_WEEKS))

    writer = AssignmentWriter(session, cid)
    tz = ZoneInfo(spec.timezone)
    now_local = datetime.combine(today, datetime.min.time(), tzinfo=tz)
    for a in spec.assignments:
        gathering_id = session.scalar(
            select(Gathering.id)
            .where(
                Gathering.church_id == cid,
                Gathering.gathering_type_id == gathering_types[a.gathering_type].id,
                Gathering.start_at >= now_local,
            )
            .order_by(Gathering.start_at)
            .limit(1)
        )
        assert gathering_id is not None, f"no upcoming {a.gathering_type} gathering"
        writer.create(
            gathering_id=gathering_id,
            ministry_id=ministries[a.ministry].id,
            role_id=roles[(a.ministry, a.role)].id,
            person_id=people[a.person].id,
            status=AssignmentStatus.APPROVED,
            source=AssignmentSource.LEADER,
        )

    AuditLogRepository(session, cid).append(
        actor="seed",
        action="seed.load_church",
        target_type="church",
        target_id=str(cid),
        after={"name": spec.name, "people": len(people), "ministries": len(ministries)},
    )
    session.flush()
    return church, True
