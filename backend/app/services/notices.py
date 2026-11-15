"""Leader notices: what a volunteer's answer left for her leader to see once.

Whether a notice has been dealt with since, and the place a "can serve" notice lets the
leader fill with one tap. The record is only read here: `put_in.py` and ApprovalService
make the change. Dismissing deletes the notice itself.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Assignment, Gathering, LeaderNotice, Person, Role, RoleMinimum
from app.db.repositories.notices import NoticeWriter
from app.db.repositories.reads import is_ministry_leader, ministries_led
from app.domain.enums import AssignmentStatus
from app.domain.schemas import NoticeOut, PutIn
from app.services.errors import NotAllowed, NotFound
from app.services.text import and_list


def notice_settled(session: Session, notice: LeaderNotice) -> tuple[bool, str | None]:
    """Whether the place a notice is about has been dealt with since, and how.

    A decline is settled once the role is back at its minimum for that gathering; "can't
    commit" once the volunteer answers the reminder after all; "can serve" once the
    leader has put them in.
    """
    if notice.kind == "can_serve":
        return (
            (True, f"{notice.text.split(' ')[0]} is on the roster.")
            if _holds_place(session, notice)
            else (False, None)
        )
    if notice.assignment_id is None:
        return False, None
    a = session.get(Assignment, notice.assignment_id)
    if a is None:
        return False, None
    first = notice.text.split(" ")[0]
    if notice.kind == "cant_commit":
        if a.status is AssignmentStatus.CONFIRMED:
            return True, f"{first} has since said yes."
        if a.status is AssignmentStatus.DECLINED:
            return True, f"{first} has since replied: can't make it."
        return False, None
    if notice.kind != "declined":
        return False, None
    gathering = session.get_one(Gathering, a.gathering_id)
    minimum = (
        session.scalar(
            select(RoleMinimum.minimum).where(
                RoleMinimum.church_id == a.church_id,
                RoleMinimum.role_id == a.role_id,
                RoleMinimum.gathering_type_id == gathering.gathering_type_id,
            )
        )
        or 0
    )
    serving = session.execute(
        select(Person.name, Assignment.created_at)
        .join(Person, Person.id == Assignment.person_id)
        .where(
            Assignment.church_id == a.church_id,
            Assignment.gathering_id == a.gathering_id,
            Assignment.role_id == a.role_id,
            Assignment.status != AssignmentStatus.DECLINED,
        )
    ).all()
    if len(serving) < minimum:
        return False, None
    newcomers = [name for name, created in serving if created >= notice.created_at]
    return True, (
        f"Covered: {and_list(newcomers)} {'is' if len(newcomers) == 1 else 'are'} in."
        if newcomers
        else "Covered."
    )


def _holds_place(session: Session, notice: LeaderNotice) -> bool:
    return (
        notice.gathering_id is not None
        and session.scalar(
            select(Assignment.id).where(
                Assignment.church_id == notice.church_id,
                Assignment.person_id == notice.about_person_id,
                Assignment.gathering_id == notice.gathering_id,
                Assignment.role_id == notice.role_id,
                Assignment.status != AssignmentStatus.DECLINED,
            )
        )
        is not None
    )


def notice_put_in(session: Session, notice: LeaderNotice, name: str) -> PutIn | None:
    """For "can serve": the place, so the leader can put them in with one tap. If they were
    asked to take someone's place and that person still holds it, it's a swap."""
    if notice.kind != "can_serve" or notice.gathering_id is None or notice.role_id is None:
        return None
    role = session.get_one(Role, notice.role_id)
    swap = swap_from(session, notice)
    return PutIn(
        ministry_id=notice.ministry_id,
        gathering_id=notice.gathering_id,
        role_id=notice.role_id,
        role=role.name,
        person_id=notice.about_person_id,
        name=name,
        replaces=swap[1] if swap else None,
    )


def swap_from(session: Session, notice: LeaderNotice) -> tuple[Assignment, str] | None:
    """The place a "can serve" notice would take over, and its holder, if it still stands."""
    if notice.assignment_id is None:
        return None
    row = session.execute(
        select(Assignment, Person.name)
        .join(Person, Person.id == Assignment.person_id)
        .where(
            Assignment.church_id == notice.church_id,
            Assignment.id == notice.assignment_id,
            Assignment.status != AssignmentStatus.DECLINED,
            Assignment.person_id != notice.about_person_id,
        )
    ).first()
    return (row[0], row[1]) if row else None


def leader_notices(session: Session, church_id: uuid.UUID, person_id: uuid.UUID) -> list[NoticeOut]:
    """What volunteers asked Shepherd to pass on, for the ministries this person leads."""
    led = ministries_led(session, church_id, person_id)
    rows = session.execute(
        select(LeaderNotice, Person.name)
        .join(Person, Person.id == LeaderNotice.about_person_id)
        .where(LeaderNotice.church_id == church_id, LeaderNotice.ministry_id.in_(led))
        .order_by(LeaderNotice.created_at)
    ).all()
    out = []
    for n, name in rows:
        settled, update = notice_settled(session, n)
        out.append(
            NoticeOut(
                id=n.id,
                ministry_id=n.ministry_id,
                about=name,
                kind=n.kind,
                text=n.text,
                note=n.note,
                at=n.created_at,
                settled=settled,
                update=update,
                put_in=None if settled else notice_put_in(session, n, name),
            )
        )
    return out


def dismiss_notice(
    session: Session, church_id: uuid.UUID, notice_id: uuid.UUID, person_id: uuid.UUID
) -> None:
    """A leader dismisses a notice: it's deleted, including any personal note it carried.
    Notices aren't the record, so this is neither a proposal nor audited."""
    notice = session.scalar(
        select(LeaderNotice).where(
            LeaderNotice.church_id == church_id, LeaderNotice.id == notice_id
        )
    )
    if notice is None:
        raise NotFound("notice not found")
    if not is_ministry_leader(session, church_id, notice.ministry_id, person_id):
        raise NotAllowed("not your ministry")
    NoticeWriter(session, church_id).dismiss(notice_id)
