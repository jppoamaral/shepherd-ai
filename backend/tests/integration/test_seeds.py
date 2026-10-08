"""Both synthetic churches load, differ where they should, and re-seeding is a no-op."""

import uuid
from datetime import time
from zoneinfo import ZoneInfo

from sqlalchemy import any_, func, select
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.models import (
    Assignment,
    Church,
    Gathering,
    GatheringType,
    LoadRule,
    Membership,
    Ministry,
    MinistryLeader,
    Person,
    Role,
    RoleSkill,
)
from app.domain.enums import GatheringKind, Period
from seeds import seed_all
from tests.conftest import GRACE, RIVERSIDE, SEED_TODAY


def people_named(session: Session, church_id: uuid.UUID, name: str) -> list[Person]:
    return list(
        session.scalars(select(Person).where(Person.church_id == church_id, Person.name == name))
    )


def ministries_of(session: Session, person: Person) -> set[str]:
    return set(
        session.scalars(
            select(Ministry.name)
            .join(Membership, Membership.ministry_id == Ministry.id)
            .where(Membership.person_id == person.id)
        )
    )


def test_both_churches_seed_with_realistic_sizes(
    session: Session, grace_id: uuid.UUID, riverside_id: uuid.UUID
) -> None:
    def count(model: type[Base], cid: uuid.UUID) -> int:
        return (
            session.scalar(
                select(func.count()).select_from(model).where(model.church_id == cid)  # type: ignore[attr-defined]
            )
            or 0
        )

    assert 35 <= count(Person, grace_id) <= 50
    assert 65 <= count(Person, riverside_id) <= 75
    for cid in (grace_id, riverside_id):
        names = set(session.scalars(select(Ministry.name).where(Ministry.church_id == cid)))
        assert names == {"Worship", "Kids", "Media", "Hospitality"}
    assert session.get_one(Church, riverside_id).member_count == 800
    assert session.get_one(Church, grace_id).member_count == 150


def test_churches_have_different_load_rules(
    session: Session, grace_id: uuid.UUID, riverside_id: uuid.UUID
) -> None:
    def rules(cid: uuid.UUID) -> list[tuple[Period, int, int]]:
        return [
            (r.period, r.normal_max, r.warning_above)
            for r in session.scalars(select(LoadRule).where(LoadRule.church_id == cid))
        ]

    assert rules(grace_id) == [(Period.WEEK, 1, 2)]  # serving weekly is normal
    assert rules(riverside_id) == [(Period.MONTH, 2, 2)]  # more than twice a month warns


def test_a_church_may_have_weekly_and_monthly_rules_or_none(
    session: Session, grace_id: uuid.UUID
) -> None:
    session.add(LoadRule(church_id=grace_id, period=Period.MONTH, normal_max=4, warning_above=5))
    session.flush()
    assert session.scalar(select(func.count()).where(LoadRule.church_id == grace_id)) == 2

    church = Church(name="No Rules Chapel", timezone="UTC")
    session.add(church)
    session.flush()
    assert session.scalar(select(func.count()).where(LoadRule.church_id == church.id)) == 0


def test_story_people_are_in_grace(session: Session, grace_id: uuid.UUID) -> None:
    for name in ["Sarah Collins", "David Morales", "Anna Parker", "Anna Peterson",
                 "Rachel Turner", "Emily Brooks", "Megan Lee", "Hannah Wright"]:  # fmt: skip
        assert len(people_named(session, grace_id, name)) == 1, name

    (anna,) = people_named(session, grace_id, "Anna Parker")
    assert ministries_of(session, anna) == {"Worship", "Kids"}

    anna_p = session.scalars(
        select(Person.name).where(Person.church_id == grace_id, any_(Person.nicknames) == "Anna P.")
    ).all()
    assert sorted(anna_p) == ["Anna Parker", "Anna Peterson"]  # the intake ambiguity case

    leaders = dict(
        session.execute(
            select(Ministry.name, Person.name)
            .join(MinistryLeader, MinistryLeader.ministry_id == Ministry.id)
            .join(Person, Person.id == MinistryLeader.person_id)
            .where(Ministry.church_id == grace_id, MinistryLeader.can_schedule)
        ).all()
    )
    assert leaders["Kids"] == "Sarah Collins"
    assert leaders["Worship"] == "David Morales"


def test_experience_is_always_set_by_a_leader_of_that_ministry(session: Session) -> None:
    """Rule 7: RoleSkill.set_by is a leader of the membership's ministry."""
    orphans = session.execute(
        select(RoleSkill.id)
        .join(Membership, Membership.id == RoleSkill.membership_id)
        .outerjoin(
            MinistryLeader,
            (MinistryLeader.ministry_id == Membership.ministry_id)
            & (MinistryLeader.person_id == RoleSkill.set_by_person_id),
        )
        .where(MinistryLeader.id.is_(None))
    ).all()
    assert orphans == []


def test_every_role_with_a_minimum_has_people_and_a_veteran(session: Session) -> None:
    rows = session.execute(
        select(
            Role.name,
            func.count(RoleSkill.id),
            func.count().filter(RoleSkill.experience == "veteran"),
        )
        .outerjoin(RoleSkill, RoleSkill.role_id == Role.id)
        .group_by(Role.id)
    ).all()
    assert rows
    for role, people, veterans in rows:
        assert people >= 2, role
        assert veterans >= 1, role


def test_gathering_types_match_each_church(
    session: Session, grace_id: uuid.UUID, riverside_id: uuid.UUID
) -> None:
    def types(cid: uuid.UUID) -> dict[str, GatheringType]:
        return {
            t.name: t
            for t in session.scalars(select(GatheringType).where(GatheringType.church_id == cid))
        }

    grace = types(grace_id)
    assert set(grace) == {
        "Sunday 9:30 Service", "Sunday 11:00 Service", "Wednesday Prayer Night", "Wednesday Youth"
    }  # fmt: skip
    assert grace["Wednesday Prayer Night"].duration_minutes >= 60

    river = types(riverside_id)
    assert {"Friday Youth Night", "Christmas Eve Service"} <= set(river)
    christmas = river["Christmas Eve Service"]
    assert christmas.kind is GatheringKind.SPECIAL
    (gathering,) = session.scalars(
        select(Gathering).where(Gathering.gathering_type_id == christmas.id)
    ).all()
    local = gathering.start_at.astimezone(ZoneInfo("America/Los_Angeles"))
    assert (local.month, local.day, local.time()) == (12, 24, time(17, 0))


def test_grace_seeds_a_real_midweek_double_booking(session: Session, grace_id: uuid.UUID) -> None:
    """Hannah is on prayer night and youth the same Wednesday, at overlapping times."""
    (hannah,) = people_named(session, grace_id, "Hannah Wright")
    rows = session.execute(
        select(Gathering, Ministry.name)
        .join(Assignment, Assignment.gathering_id == Gathering.id)
        .join(Ministry, Ministry.id == Assignment.ministry_id)
        .where(Assignment.person_id == hannah.id)
        .order_by(Gathering.start_at)
    ).all()
    assert [m for _, m in rows] == ["Worship", "Media"]
    (a, _), (b, _) = rows
    assert a.start_at < b.end_at and b.start_at < a.end_at
    assert a.start_at.astimezone(ZoneInfo("America/Chicago")).strftime("%A") == "Wednesday"


def test_reseeding_creates_no_duplicates(session: Session) -> None:
    def counts() -> dict[str, int]:
        return {
            name: session.scalar(select(func.count()).select_from(table)) or 0
            for name, table in Base.metadata.tables.items()
            if name != "audit_log"
        }

    before = counts()
    assert seed_all(session, SEED_TODAY) == {GRACE: False, RIVERSIDE: False}
    session.flush()
    assert counts() == before
