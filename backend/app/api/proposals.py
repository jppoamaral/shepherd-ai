"""The approval queue. Approving or rejecting goes through ApprovalService only."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import ReaderDep
from app.db.models import Proposal
from app.db.repositories.reads import ChurchReader
from app.domain.enums import ProposalStatus
from app.domain.schemas import DecisionIn, ProposalOut
from app.services.approval import ApprovalService
from app.services.proposal_text import describe

router = APIRouter(tags=["proposals"])


@router.get("/churches/{church_id}/proposals")
def list_proposals(
    reader: ReaderDep, status_: Annotated[ProposalStatus | None, Query(alias="status")] = None
) -> list[ProposalOut]:
    return describe(reader.session, reader.church_id, reader.proposals(status_))


@router.post("/churches/{church_id}/proposals/{proposal_id}/approve")
def approve(reader: ReaderDep, proposal_id: uuid.UUID, body: DecisionIn) -> ProposalOut:
    service = ApprovalService(reader.session)
    return _decided(reader, service.approve(reader.church_id, proposal_id, body.person_id))


@router.post("/churches/{church_id}/proposals/{proposal_id}/reject")
def reject(reader: ReaderDep, proposal_id: uuid.UUID, body: DecisionIn) -> ProposalOut:
    service = ApprovalService(reader.session)
    return _decided(reader, service.reject(reader.church_id, proposal_id, body.person_id))


def _decided(reader: ChurchReader, proposal: Proposal) -> ProposalOut:
    reader.session.commit()
    (described,) = describe(
        reader.session, reader.church_id, [ProposalOut.model_validate(proposal)]
    )
    return described
