"""A ministry's roster suggestion, and approving the leader's (possibly edited) version."""

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from app.api.routes import ReaderDep
from app.domain.schemas import ProposalOut, SuggestionApprove, SuggestionOut
from app.services.briefing import church_today
from app.services.errors import ApprovalError, NotAllowed, NotFound
from app.services.proposal_text import describe
from app.services.suggestion import approve_suggestion, suggest

router = APIRouter(tags=["rosters"])


@router.get("/churches/{church_id}/ministries/{ministry_id}/suggestion")
def get_suggestion(
    reader: ReaderDep,
    ministry_id: uuid.UUID,
    start: Annotated[date | None, Query(description="Church-local date; defaults to today")] = None,
) -> SuggestionOut:
    """Shepherd's suggested roster for the ministry's drafting horizon. Nothing is saved."""
    result = suggest(
        reader.session,
        reader.church_id,
        ministry_id,
        start or church_today(reader.session, reader.church_id),
    )
    if result is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ministry not found")
    return result


@router.post("/churches/{church_id}/ministries/{ministry_id}/suggestion/approve")
def approve(reader: ReaderDep, ministry_id: uuid.UUID, body: SuggestionApprove) -> ProposalOut:
    """Approve the roster as the leader edited it. Recorded through the approval queue."""
    session = reader.session
    try:
        proposal = approve_suggestion(
            session, reader.church_id, ministry_id, body.person_id, body.assignments
        )
    except NotFound as error:
        session.rollback()
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error
    except NotAllowed as error:
        session.rollback()
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(error)) from error
    except ApprovalError as error:
        session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
    session.commit()
    (described,) = describe(session, reader.church_id, [ProposalOut.model_validate(proposal)])
    return described
