""" "Put … in" on a leader's notice: someone said yes when asked to serve a place.

The leader's tap approves a proposal applied by ApprovalService. If they were asked to
take another person's place and that person still holds it, it's a swap (as the huddle's
Resolve does); otherwise they're added to that place on the roster.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import LeaderNotice, Person
from app.db.repositories.proposals import ProposalRepository
from app.domain.schemas import PutInOut, SuggestedAssignment
from app.services.approval import ApprovalService
from app.services.errors import ApprovalError, NotFound
from app.services.inbound import notice_put_in, notice_settled, swap_from
from app.services.serve_ask import SWAP_TYPE
from app.services.suggestion import approve_suggestion


def put_in(
    session: Session, church_id: uuid.UUID, notice_id: uuid.UUID, leader_id: uuid.UUID
) -> PutInOut:
    notice = session.scalar(
        select(LeaderNotice).where(
            LeaderNotice.church_id == church_id, LeaderNotice.id == notice_id
        )
    )
    if notice is None:
        raise NotFound("notice not found")
    name = session.get_one(Person, notice.about_person_id).name
    place = notice_put_in(session, notice, name)
    if place is None:
        raise NotFound("this notice has no place to fill")
    if notice_settled(session, notice)[0]:
        raise ApprovalError(f"{name.split(' ')[0]} is already on the roster.")
    swap = swap_from(session, notice)
    if swap is None:
        approve_suggestion(
            session,
            church_id,
            place.ministry_id,
            leader_id,
            [
                SuggestedAssignment(
                    gathering_id=place.gathering_id,
                    role_id=place.role_id,
                    person_id=place.person_id,
                    reason="Said yes when asked.",
                )
            ],
        )
        return PutInOut(text=f"{name} is on the roster as {place.role}.")
    assignment, holder = swap
    proposal = ProposalRepository(session, church_id).create(
        type=SWAP_TYPE,
        payload={
            "ministry_id": str(place.ministry_id),
            "assignment_id": str(assignment.id),
            "from_person_id": str(assignment.person_id),
            "to_person_id": str(place.person_id),
        },
        created_by_agent="steward",
    )
    ApprovalService(session).approve(church_id, proposal.id, leader_id)
    return PutInOut(text=f"{name} is in {holder.split(' ')[0]}'s place as {place.role}.")
