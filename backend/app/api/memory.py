"""Leader memory: what Shepherd remembers for a ministry, and "Should I remember this?"."""

import uuid
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Response, status

from app.api.routes import ReaderDep
from app.domain.enums import MemorySource
from app.domain.schemas import MemoryNote, MemoryOut, MemoryPendingOut
from app.services.memory import (
    MemoryNotAllowed,
    MemoryRefused,
    delete_memory,
    is_leader,
    memory_view,
    propose_memory,
)

router = APIRouter(tags=["memory"])


@router.get("/churches/{church_id}/ministries/{ministry_id}/memory")
def get_memory(reader: ReaderDep, ministry_id: uuid.UUID) -> MemoryOut:
    """Confirmed memories, plus the ones waiting for "Should I remember this?"."""
    result = memory_view(reader.session, reader.church_id, ministry_id)
    if result is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ministry not found")
    return result


@router.post(
    "/churches/{church_id}/ministries/{ministry_id}/memory/notes",
    status_code=status.HTTP_201_CREATED,
)
def note(reader: ReaderDep, ministry_id: uuid.UUID, body: MemoryNote) -> MemoryPendingOut:
    """A leader's note becomes a memory proposal to confirm; private content is refused."""
    session = reader.session
    if not is_leader(session, reader.church_id, ministry_id, body.person_id):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "only this ministry's leaders can add memories"
        )
    try:
        proposal = propose_memory(
            session,
            reader.church_id,
            ministry_id=ministry_id,
            text=body.text,
            kind=body.kind,
            proposed_from=MemorySource.LEADER_NOTE,
            about_person_id=body.about_person_id,
        )
    except MemoryRefused as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from error
    session.commit()
    view = memory_view(session, reader.church_id, ministry_id)
    assert view is not None
    return next(p for p in view.pending if p.proposal_id == proposal.id)


@router.delete(
    "/churches/{church_id}/ministries/{ministry_id}/memory/{memory_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def forget(
    reader: ReaderDep,
    ministry_id: uuid.UUID,
    memory_id: uuid.UUID,
    person_id: Annotated[uuid.UUID, Query(description="The leader deleting it")],
) -> Response:
    try:
        delete_memory(reader.session, reader.church_id, ministry_id, memory_id, person_id)
    except MemoryNotAllowed as error:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(error)) from error
    except LookupError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error
    reader.session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
