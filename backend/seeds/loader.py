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
    Assignment,
    Blockout,
    Church,
    Gathering,
    GatheringType,
    LeaderAvailability,
    LoadRule,
    Membership,
    MemoryItem,
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
    Experience,
    ProfileStatus,
    Recurrence,
    StatedBy,
)
from app.services.gatherings import ensure_gatherings
from app.services.memory import propose_memory
from seeds.generate import generate_volunteers
from seeds.spec import ChurchSeed, PersonSeed, demo_sunday

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
        channel=spec.channel,
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
            start, end = b.dates(today)
            session.add(
                Blockout(
                    church_id=cid,
                    person_id=person.id,
                    start_date=start,
                    end_date=end,
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
    # The demo week starts at the first upcoming Sunday, so a Sunday and the
    # Wednesday after it fall in the same (Sunday-to-Saturday) church week.
    now_local = datetime.combine(demo_sunday(today), datetime.min.time(), tzinfo=tz)
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

    _fill_rosters(
        session,
        spec,
        cid,
        people_specs,
        people,
        ministries,
        roles,
        gathering_types,
        now_local,
        today,
    )

    for memory in spec.memories:
        about = people[memory.about].id if memory.about else None
        if memory.confirmed_by:
            session.add(
                MemoryItem(
                    church_id=cid,
                    ministry_id=ministries[memory.ministry].id,
                    about_person_id=about,
                    kind=memory.kind,
                    text=memory.text,
                    proposed_from=memory.proposed_from,
                    confirmed_by_person_id=people[memory.confirmed_by].id,
                )
            )
        else:
            propose_memory(
                session,
                cid,
                ministry_id=ministries[memory.ministry].id,
                text=memory.text,
                kind=memory.kind,
                proposed_from=memory.proposed_from,
                about_person_id=about,
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


EXPERIENCE_ORDER = {Experience.VETERAN: 0, Experience.EXPERIENCED: 1, Experience.NEW: 2}


def _fill_rosters(
    session: Session,
    spec: ChurchSeed,
    cid: uuid.UUID,
    people_specs: list[PersonSeed],
    people: dict[str, Person],
    ministries: dict[str, Ministry],
    roles: dict[tuple[str, str], Role],
    gathering_types: dict[str, GatheringType],
    week_start: datetime,
    today: date,
) -> None:
    """Fill demo-week rosters up to their minimums, deterministically.

    Picks the most experienced free team members first, at most one fill per person
    in the week, never at an overlapping time or on a blockout date, so the only
    warnings in the demo are the seeded stories (and genuine leftovers).
    """
    if not spec.fill_rosters:
        return
    week_end = week_start + timedelta(days=7)
    rows = session.execute(
        select(Assignment.person_id, Assignment.gathering_id, Assignment.role_id)
        .join(Gathering, Gathering.id == Assignment.gathering_id)
        .where(
            Assignment.church_id == cid,
            Gathering.start_at >= week_start,
            Gathering.start_at < week_end,
        )
    ).all()
    serving: set[uuid.UUID] = set()
    filled: dict[tuple[uuid.UUID, uuid.UUID], int] = {}
    for person_id, gathering_id, role_id in rows:
        serving.add(person_id)
        filled[(gathering_id, role_id)] = filled.get((gathering_id, role_id), 0) + 1
    blocked = {p.key: [b.dates(today) for b in p.blockouts] for p in people_specs}
    minimums = {(m.name, r.name): r.minimums for m in spec.ministries for r in m.roles}
    writer = AssignmentWriter(session, cid)

    for ministry_name, gt_key in spec.fill_rosters:
        gathering = session.scalar(
            select(Gathering)
            .where(
                Gathering.church_id == cid,
                Gathering.gathering_type_id == gathering_types[gt_key].id,
                Gathering.start_at >= week_start,
            )
            .order_by(Gathering.start_at)
            .limit(1)
        )
        assert gathering is not None
        local_day = gathering.start_at.astimezone(week_start.tzinfo).date()
        for (m_name, role_name), mins in minimums.items():
            if m_name != ministry_name or not mins.get(gt_key):
                continue
            role = roles[(m_name, role_name)]
            candidates = sorted(
                (p for p in people_specs if role_name in p.skills.get(m_name, {})),
                key=lambda p: (EXPERIENCE_ORDER[p.skills[m_name][role_name]], p.name),
            )
            for candidate in candidates:
                if filled.get((gathering.id, role.id), 0) >= mins[gt_key]:
                    break
                person = people[candidate.key]
                if person.id in serving or any(
                    a <= local_day <= b for a, b in blocked[candidate.key]
                ):
                    continue  # one fill per person per week; never on a blockout date
                writer.create(
                    gathering_id=gathering.id,
                    ministry_id=ministries[m_name].id,
                    role_id=role.id,
                    person_id=person.id,
                    status=AssignmentStatus.APPROVED,
                    source=AssignmentSource.LEADER,
                )
                serving.add(person.id)
                filled[(gathering.id, role.id)] = filled.get((gathering.id, role.id), 0) + 1
