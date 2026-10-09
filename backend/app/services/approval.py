"""ApprovalService: the ONLY code allowed to apply a Proposal's side effects.

Every approval or rejection writes an AuditLog entry (architecture rules 1 and 9).
Each proposal type has a handler that says who may decide it and how to apply
it. Handlers are invoked only from here; `tests/unit/test_architecture.py`
checks that nothing else imports them.
"""

import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Person, Proposal
from app.db.repositories.audit import AuditLogRepository
from app.domain.enums import ProposalStatus
from app.services import (
    huddle_apply,
    memory_apply,
    profile_apply,
    reminders_apply,
    reply_apply,
    roster_apply,
    serve_ask_apply,
)
from app.services.errors import ApprovalError, NotAllowed, NotFound


@dataclass(frozen=True)
class ProposalHandler:
    # Whether this person may approve or reject the proposal.
    may_decide: Callable[[Session, Proposal, Person], bool]
    # Apply the side effects; returns a summary for the audit log.
    apply: Callable[[Session, Proposal, Person], dict[str, Any]]
    # Optional cleanup after a rejection (nothing in the record changes).
    on_reject: Callable[[Session, Proposal], None] | None = None


HANDLERS: Mapping[str, ProposalHandler] = {
    profile_apply.PROPOSAL_TYPE: ProposalHandler(
        may_decide=profile_apply.may_decide,
        apply=profile_apply.apply,
        on_reject=profile_apply.on_reject,
    ),
    roster_apply.PROPOSAL_TYPE: ProposalHandler(
        may_decide=roster_apply.may_decide,
        apply=roster_apply.apply,
        on_reject=roster_apply.on_reject,
    ),
    memory_apply.PROPOSAL_TYPE: ProposalHandler(
        may_decide=memory_apply.may_decide, apply=memory_apply.apply
    ),
    huddle_apply.ACCEPT_TYPE: ProposalHandler(
        may_decide=huddle_apply.may_decide, apply=huddle_apply.apply_accept
    ),
    huddle_apply.UNDO_TYPE: ProposalHandler(
        may_decide=huddle_apply.may_decide, apply=huddle_apply.apply_undo
    ),
    reminders_apply.PROPOSAL_TYPE: ProposalHandler(
        may_decide=reminders_apply.may_decide, apply=reminders_apply.apply
    ),
    serve_ask_apply.PROPOSAL_TYPE: ProposalHandler(
        may_decide=serve_ask_apply.may_decide, apply=serve_ask_apply.apply
    ),
    **{
        kind: ProposalHandler(may_decide=reply_apply.may_decide, apply=reply_apply.apply)
        for kind in reply_apply.TYPES
    },
}


class ApprovalService:
    def __init__(
        self, session: Session, handlers: Mapping[str, ProposalHandler] = HANDLERS
    ) -> None:
        self.session = session
        self.handlers = handlers

    def approve(
        self, church_id: uuid.UUID, proposal_id: uuid.UUID, person_id: uuid.UUID
    ) -> Proposal:
        proposal, person, handler = self._load(church_id, proposal_id, person_id)
        summary = handler.apply(self.session, proposal, person)
        self._decide(proposal, person, ProposalStatus.APPROVED, summary)
        return proposal

    def reject(
        self, church_id: uuid.UUID, proposal_id: uuid.UUID, person_id: uuid.UUID
    ) -> Proposal:
        proposal, person, handler = self._load(church_id, proposal_id, person_id)
        if handler.on_reject is not None:
            handler.on_reject(self.session, proposal)
        self._decide(proposal, person, ProposalStatus.REJECTED, {})
        return proposal

    def _load(
        self, church_id: uuid.UUID, proposal_id: uuid.UUID, person_id: uuid.UUID
    ) -> tuple[Proposal, Person, ProposalHandler]:
        proposal = self.session.scalar(
            select(Proposal)
            .where(Proposal.church_id == church_id, Proposal.id == proposal_id)
            .with_for_update()
        )
        if proposal is None:
            raise NotFound("proposal not found")
        person = self.session.scalar(
            select(Person).where(Person.church_id == church_id, Person.id == person_id)
        )
        if person is None:
            raise NotFound("person not found")
        if proposal.status is not ProposalStatus.PENDING:
            raise ApprovalError(f"this proposal was already {proposal.status}")
        handler = self.handlers.get(proposal.type)
        if handler is None:
            raise ApprovalError(f"no handler for proposals of type {proposal.type!r}")
        if not handler.may_decide(self.session, proposal, person):
            raise NotAllowed(f"{person.name} can't decide this proposal")
        return proposal, person, handler

    def _decide(
        self,
        proposal: Proposal,
        person: Person,
        status: ProposalStatus,
        summary: dict[str, Any],
    ) -> None:
        proposal.status = status
        proposal.decided_by_person_id = person.id
        proposal.decided_at = datetime.now(UTC)
        AuditLogRepository(self.session, proposal.church_id).append(
            actor=f"person:{person.id}",
            action=f"proposal.{status}",
            target_type=f"proposal:{proposal.type}",
            target_id=str(proposal.id),
            before={"status": ProposalStatus.PENDING.value},
            after={
                "status": status.value,
                "created_by_agent": proposal.created_by_agent,
                **summary,
            },
            approved_by_person_id=person.id if status is ProposalStatus.APPROVED else None,
        )
        self.session.flush()
