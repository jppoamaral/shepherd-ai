"""The one write path open to agents: recording a pending Proposal."""

import uuid

from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.models import Proposal
from app.domain.enums import ProposalStatus, ProposalType
from app.domain.proposals import PAYLOADS, ProposalPayload


class ProposalRepository:
    def __init__(self, session: Session, church_id: uuid.UUID) -> None:
        self.session = session
        self.church_id = church_id

    def create(self, *, type: ProposalType, payload: BaseModel, created_by_agent: str) -> Proposal:
        """`payload` must be the model `PAYLOADS` names for this type."""
        expected = PAYLOADS[type]
        if not isinstance(payload, expected):
            raise TypeError(f"a {type.value} proposal carries {expected.__name__}")
        stored = (
            payload.stored()
            if isinstance(payload, ProposalPayload)
            else payload.model_dump(mode="json")
        )
        proposal = Proposal(
            church_id=self.church_id,
            type=type.value,
            payload=stored,
            created_by_agent=created_by_agent,
            status=ProposalStatus.PENDING,
        )
        self.session.add(proposal)
        self.session.flush()
        return proposal
