"""Applies an approved `memory` proposal. Called only by ApprovalService."""

from typing import Any

from sqlalchemy.orm import Session

from app.db.models import MemoryItem, Person, Proposal
from app.db.repositories.reads import is_ministry_leader
from app.domain.proposals import MemoryPayload
from app.domain.schemas import ProposalOut
from app.services.errors import ApprovalError
from app.services.memory import private_reason
from app.services.names import Names, ProposalText


def may_decide(session: Session, proposal: Proposal, person: Person) -> bool:
    """Any leader of the memory's ministry may confirm it."""
    payload = MemoryPayload.model_validate(proposal.payload)
    return is_ministry_leader(session, proposal.church_id, payload.ministry_id, person.id)


def describe(names: Names, proposal: ProposalOut) -> ProposalText:
    payload = MemoryPayload.model_validate(proposal.payload)
    about = f" about {names.person(payload.about_person_id)}" if payload.about_person_id else ""
    return ProposalText(
        title=f"Should I remember this? ({names.ministry(payload.ministry_id)})",
        summary=f"“{payload.text}”{about}",
    )


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
