"""Applies an approved `memory` proposal. Called only by ApprovalService."""

from typing import Any

from sqlalchemy.orm import Session

from app.db.models import MemoryItem, Person, Proposal
from app.domain.proposals import MemoryPayload
from app.services.errors import ApprovalError
from app.services.memory import is_leader, private_reason


def may_decide(session: Session, proposal: Proposal, person: Person) -> bool:
    """Any leader of the memory's ministry may confirm it."""
    payload = MemoryPayload.model_validate(proposal.payload)
    return is_leader(session, proposal.church_id, payload.ministry_id, person.id)


def apply(session: Session, proposal: Proposal, approver: Person) -> dict[str, Any]:
    payload = MemoryPayload.model_validate(proposal.payload)
    if reason := private_reason(payload.text):
        raise ApprovalError(reason)
    item = MemoryItem(
        church_id=proposal.church_id,
        ministry_id=payload.ministry_id,
        about_person_id=payload.about_person_id,
        kind=payload.kind,
        text=payload.text,
        proposed_from=payload.proposed_from,
        confirmed_by_person_id=approver.id,
    )
    session.add(item)
    session.flush()
    return {"memory_id": str(item.id), "kind": item.kind.value}
