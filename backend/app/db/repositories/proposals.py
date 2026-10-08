"""The one write path open to agents: recording a pending Proposal."""

import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import Proposal
from app.domain.enums import ProposalStatus


class ProposalRepository:
    def __init__(self, session: Session, church_id: uuid.UUID) -> None:
        self.session = session
        self.church_id = church_id

    def create(self, *, type: str, payload: dict[str, Any], created_by_agent: str) -> Proposal:
        proposal = Proposal(
            church_id=self.church_id,
            type=type,
            payload=payload,
            created_by_agent=created_by_agent,
            status=ProposalStatus.PENDING,
        )
        self.session.add(proposal)
        self.session.flush()
        return proposal
