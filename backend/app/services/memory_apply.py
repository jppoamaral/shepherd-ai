"""Applies an approved `memory` proposal. Called only by ApprovalService."""

import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import MemoryItem, Person, Proposal
from app.domain.enums import MemoryKind, MemorySource
from app.services.errors import ApprovalError
from app.services.memory import PROPOSAL_TYPE, is_leader, private_reason

__all__ = ["PROPOSAL_TYPE", "apply", "may_decide"]


def may_decide(session: Session, proposal: Proposal, person: Person) -> bool:
    """Any leader of the memory's ministry may confirm it."""
    return is_leader(
        session, proposal.church_id, uuid.UUID(proposal.payload["ministry_id"]), person.id
    )


def apply(session: Session, proposal: Proposal, approver: Person) -> dict[str, Any]:
    payload = proposal.payload
    if reason := private_reason(payload["text"]):
        raise ApprovalError(reason)
    item = MemoryItem(
        church_id=proposal.church_id,
        ministry_id=uuid.UUID(payload["ministry_id"]),
        about_person_id=uuid.UUID(payload["about_person_id"])
        if payload.get("about_person_id")
        else None,
        kind=MemoryKind(payload["kind"]),
        text=payload["text"],
        proposed_from=MemorySource(payload["proposed_from"]),
        confirmed_by_person_id=approver.id,
    )
    session.add(item)
    session.flush()
    return {"memory_id": str(item.id), "kind": item.kind.value}
