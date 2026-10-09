"""Applies a volunteer's own answer: yes, can't make it, away dates, stop, start, and her
answer to a leader asking her to serve.

Each is a proposal the volunteer's reply approves (she decides about herself), applied
here and audited by ApprovalService like any other change. Called only by ApprovalService.
Payloads hold ids, dates and statuses only; never what the volunteer wrote.
"""

import uuid
from datetime import date, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Assignment, Blockout, Gathering, Message, Person, Proposal
from app.db.repositories.assignments import AssignmentWriter
from app.db.repositories.messages import MessageWriter
from app.domain.enums import AssignmentStatus, StatedBy
from app.services.briefing import church_today
from app.services.checks_runner import run_checks
from app.services.errors import ApprovalError
from app.services.reply_types import AWAY, CAN_SERVE, CANT_SERVE, CONFIRM, START, STOP, TYPES

__all__ = ["TYPES", "apply", "may_decide"]


def may_decide(session: Session, proposal: Proposal, person: Person) -> bool:
    """Only the volunteer the answer is about."""
    return str(person.id) == str(proposal.payload["person_id"])


def apply(session: Session, proposal: Proposal, volunteer: Person) -> dict[str, Any]:
    cid = proposal.church_id
    payload = proposal.payload
    if proposal.type in (STOP, START):
        volunteer.stopped = proposal.type == STOP
        session.flush()
        return {"stopped": volunteer.stopped}
    if proposal.type == AWAY:
        days = sorted(date.fromisoformat(d) for d in payload["dates"])
        for day in days:
            session.add(
                Blockout(
                    church_id=cid,
                    person_id=volunteer.id,
                    start_date=day,
                    end_date=day,
                    stated_by=StatedBy.VOLUNTEER,
                )
            )
        session.flush()
        run_checks(session, cid, days[0] - timedelta(days=7), days[-1] + timedelta(days=7))
        return {"dates": [d.isoformat() for d in days]}
    if proposal.type in (CAN_SERVE, CANT_SERVE):
        # Her answer only marks the ask answered; the roster changes when a leader puts her in.
        message = session.scalar(
            select(Message).where(
                Message.church_id == cid,
                Message.id == uuid.UUID(payload["message_id"]),
                Message.person_id == volunteer.id,
                Message.kind == "ask",
            )
        )
        if message is None or message.answered_at is not None:
            raise ApprovalError("That ask was already answered.")
        MessageWriter(session, cid).answered(message)
        return {"message_id": str(message.id), "can_serve": proposal.type == CAN_SERVE}

    assignment = session.scalar(
        select(Assignment).where(
            Assignment.church_id == cid,
            Assignment.id == uuid.UUID(payload["assignment_id"]),
            Assignment.person_id == volunteer.id,
        )
    )
    if assignment is None or assignment.status is AssignmentStatus.DECLINED:
        raise ApprovalError("That place has changed since the reminder.")
    status = AssignmentStatus.CONFIRMED if proposal.type == CONFIRM else AssignmentStatus.DECLINED
    before = assignment.status.value
    AssignmentWriter(session, cid).set_status(assignment, status)
    if status is AssignmentStatus.DECLINED:
        # A decline re-runs the checks and reports the new gap (brief §5 step 6).
        start = session.get_one(Gathering, assignment.gathering_id).start_at.date()
        today = church_today(session, cid)
        run_checks(session, cid, min(today, start) - timedelta(days=7), start + timedelta(days=7))
    return {"assignment_id": str(assignment.id), "from": before, "to": status.value}
