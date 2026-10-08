"""Rule 3: every read is church-scoped, and the schema refuses cross-church links."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import (
    Assignment,
    Gathering,
    Membership,
    Ministry,
    Person,
    Role,
)
from app.db.repositories.reads import ChurchReader
from app.domain.enums import AssignmentSource, AssignmentStatus

TenantModel = Person | Ministry | Role | Gathering

WIDE_WINDOW = (datetime(2026, 1, 1, tzinfo=UTC), datetime(2028, 1, 1, tzinfo=UTC))


def ids(session: Session, model: type[TenantModel], cid: uuid.UUID) -> set[uuid.UUID]:
    return set(session.scalars(select(model.id).where(model.church_id == cid)))


def test_reader_returns_only_its_own_church(
    session: Session, grace_id: uuid.UUID, riverside_id: uuid.UUID
) -> None:
    grace = ChurchReader(session, grace_id)
    assert {p.id for p in grace.people()} == ids(session, Person, grace_id)
    assert {m.id for m in grace.ministries()} == ids(session, Ministry, grace_id)
    assert {g.id for g in grace.gatherings(*WIDE_WINDOW)} == ids(session, Gathering, grace_id)

    riverside_people = ids(session, Person, riverside_id)
    assert riverside_people
    assert not {p.id for p in grace.people()} & riverside_people


def test_api_never_mixes_churches(
    client: TestClient, session: Session, grace_id: uuid.UUID, riverside_id: uuid.UUID
) -> None:
    grace_people = {p["id"] for p in client.get(f"/churches/{grace_id}/people").json()}
    river_people = {p["id"] for p in client.get(f"/churches/{riverside_id}/people").json()}
    assert grace_people and river_people
    assert not grace_people & river_people
    assert grace_people == {str(i) for i in ids(session, Person, grace_id)}

    params = {"from": WIDE_WINDOW[0].isoformat(), "to": WIDE_WINDOW[1].isoformat()}
    grace_gatherings = client.get(f"/churches/{grace_id}/gatherings", params=params).json()
    assert {g["id"] for g in grace_gatherings} == {
        str(i) for i in ids(session, Gathering, grace_id)
    }


def test_unknown_church_is_404(client: TestClient) -> None:
    for path in ["", "/people", "/ministries", "/gatherings", "/gathering-types"]:
        assert client.get(f"/churches/{uuid.uuid4()}{path}").status_code == 404


def first[T: (Person, Ministry, Role, Gathering)](
    session: Session, model: type[T], cid: uuid.UUID
) -> T:
    row = session.scalars(select(model).where(model.church_id == cid)).first()
    assert row is not None
    return row


def test_database_rejects_membership_across_churches(
    session: Session, grace_id: uuid.UUID, riverside_id: uuid.UUID
) -> None:
    grace_person = first(session, Person, grace_id)
    river_ministry = first(session, Ministry, riverside_id)
    with pytest.raises(IntegrityError, match="fk_memberships_church_id_ministry_id"):
        session.add(
            Membership(
                church_id=grace_id,
                person_id=grace_person.id,
                ministry_id=river_ministry.id,
                status_since=datetime.now(UTC).date(),
            )
        )
        session.flush()


def test_database_rejects_assignment_to_another_churchs_gathering(
    session: Session, grace_id: uuid.UUID, riverside_id: uuid.UUID
) -> None:
    role = first(session, Role, grace_id)
    with pytest.raises(IntegrityError, match="fk_assignments_church_id_gathering_id"):
        session.add(
            Assignment(
                church_id=grace_id,
                gathering_id=first(session, Gathering, riverside_id).id,
                ministry_id=role.ministry_id,
                role_id=role.id,
                person_id=first(session, Person, grace_id).id,
                status=AssignmentStatus.APPROVED,
                source=AssignmentSource.LEADER,
            )
        )
        session.flush()


def test_database_rejects_a_role_from_another_ministry(
    session: Session, grace_id: uuid.UUID
) -> None:
    worship, kids = (
        session.scalar(select(Ministry).where(Ministry.church_id == grace_id, Ministry.name == n))
        for n in ("Worship", "Kids")
    )
    assert worship is not None and kids is not None
    kids_role = session.scalars(select(Role).where(Role.ministry_id == kids.id)).first()
    assert kids_role is not None
    with pytest.raises(IntegrityError, match="fk_assignments_ministry_id_role_id_roles"):
        session.add(
            Assignment(
                church_id=grace_id,
                gathering_id=first(session, Gathering, grace_id).id,
                ministry_id=worship.id,
                role_id=kids_role.id,
                person_id=first(session, Person, grace_id).id,
                status=AssignmentStatus.APPROVED,
                source=AssignmentSource.LEADER,
            )
        )
        session.flush()


def test_default_gathering_window_is_the_next_four_weeks(
    client: TestClient, grace_id: uuid.UUID
) -> None:
    gatherings = client.get(f"/churches/{grace_id}/gatherings").json()
    now = datetime.now(UTC)
    for g in gatherings:
        start = datetime.fromisoformat(g["start_at"])
        assert now <= start < now + timedelta(weeks=4)
