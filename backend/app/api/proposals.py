"""The approval queue. Approving or rejecting goes through ApprovalService only."""

import uuid
from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from app.api.routes import ReaderDep
from app.db.models import Proposal
from app.db.repositories.reads import ChurchReader
from app.domain.enums import ProposalStatus
from app.domain.schemas import DecisionIn, ProposalOut
from app.services.approval import ApprovalService
from app.services.errors import ApprovalError, NotAllowed, NotFound
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
    return _decide(reader, lambda: service.approve(reader.church_id, proposal_id, body.person_id))


@router.post("/churches/{church_id}/proposals/{proposal_id}/reject")
def reject(reader: ReaderDep, proposal_id: uuid.UUID, body: DecisionIn) -> ProposalOut:
    service = ApprovalService(reader.session)
    return _decide(reader, lambda: service.reject(reader.church_id, proposal_id, body.person_id))


def _decide(reader: ChurchReader, decide: Callable[[], Proposal]) -> ProposalOut:
    try:
        proposal = decide()
    except NotFound as error:
        reader.session.rollback()
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error
    except NotAllowed as error:
        reader.session.rollback()
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(error)) from error
    except ApprovalError as error:
        reader.session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
    reader.session.commit()
    (described,) = describe(
        reader.session, reader.church_id, [ProposalOut.model_validate(proposal)]
    )
    return described
