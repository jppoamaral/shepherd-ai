"""Leader notices: what a volunteer's answer left for her leader to see once.

Whether a notice has been dealt with since, and the place a "can serve" notice lets the
leader fill with one tap. Reads only; `put_in.py` and ApprovalService make the change.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Assignment, Gathering, LeaderNotice, Person, Role, RoleMinimum
from app.domain.enums import AssignmentStatus
from app.domain.schemas import PutIn
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
