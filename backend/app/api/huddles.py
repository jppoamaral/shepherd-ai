"""Conflict huddle: "Find a time to talk" for the two leaders of a double booking."""

import uuid
from collections.abc import Callable
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.routes import ReaderDep
from app.db.repositories.reads import ChurchReader
from app.domain.schemas import (
    HuddleAcceptReplacement,
    HuddleChoose,
    HuddleOut,
    HuddleResolve,
    HuddleStart,
    HuddleUndoReplacement,
)
from app.services.errors import ApprovalError, NotAllowed, NotFound
from app.services.huddle import (
    HuddleError,
    HuddleNotAllowed,
    HuddleNotFound,
    accept_replacement,
    choose_slot,
    get_huddle,
    resolve,
    start_huddle,
    undo_replacement,
)

router = APIRouter(tags=["huddles"])


def now_dependency() -> datetime | None:
    """Current time for slot offers; None means "now". Tests pin it."""
    return None


NowDep = Annotated[datetime | None, Depends(now_dependency)]


@router.post(
    "/churches/{church_id}/findings/{finding_id}/huddle", status_code=status.HTTP_201_CREATED
)
def start(reader: ReaderDep, finding_id: uuid.UUID, body: HuddleStart, now: NowDep) -> HuddleOut:
    """Offer 2 or 3 fifteen-minute slots both leaders are free, with a neutral agenda."""
    return _run(
        reader,
        lambda: start_huddle(reader.session, reader.church_id, finding_id, body.person_id, now),
    )


@router.get("/churches/{church_id}/huddles/{huddle_id}")
def get(reader: ReaderDep, huddle_id: uuid.UUID) -> HuddleOut:
    return _run(
        reader, lambda: get_huddle(reader.session, reader.church_id, huddle_id), commit=False
    )


@router.post("/churches/{church_id}/huddles/{huddle_id}/choose")
def choose(reader: ReaderDep, huddle_id: uuid.UUID, body: HuddleChoose) -> HuddleOut:
    return _run(
        reader,
        lambda: choose_slot(
            reader.session, reader.church_id, huddle_id, body.person_id, body.slot_id
        ),
    )


@router.post("/churches/{church_id}/huddles/{huddle_id}/resolve")
def settle(reader: ReaderDep, huddle_id: uuid.UUID, body: HuddleResolve) -> HuddleOut:
    """Send the leaders' decision back; checks re-run. Shepherd reassigns nobody."""
    return _run(
        reader,
        lambda: resolve(reader.session, reader.church_id, huddle_id, body.person_id, body.outcome),
    )


@router.post("/churches/{church_id}/huddles/{huddle_id}/accept-replacement")
def accept(reader: ReaderDep, huddle_id: uuid.UUID, body: HuddleAcceptReplacement) -> HuddleOut:
    """Resolve: put Shepherd's suggested replacement in the volunteer's place on the leader's
    own roster, through the approval queue. Nobody is messaged."""
    return _run(
        reader,
        lambda: accept_replacement(
            reader.session, reader.church_id, huddle_id, body.person_id, body.ministry_id
        ),
    )


@router.post("/churches/{church_id}/huddles/{huddle_id}/undo-replacement")
def undo(reader: ReaderDep, huddle_id: uuid.UUID, body: HuddleUndoReplacement) -> HuddleOut:
    """Undo Resolve: the volunteer goes back on the roster and the huddle reopens."""
    return _run(
        reader,
        lambda: undo_replacement(reader.session, reader.church_id, huddle_id, body.person_id),
    )


def _run(reader: ChurchReader, action: Callable[[], HuddleOut], commit: bool = True) -> HuddleOut:
    try:
        result = action()
    except (HuddleNotFound, NotFound) as error:
        reader.session.rollback()
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error
    except (HuddleNotAllowed, NotAllowed) as error:
        reader.session.rollback()
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(error)) from error
    except (HuddleError, ApprovalError) as error:
        # Nothing half-done stays behind, including the proposal itself.
        reader.session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
    if commit:
        reader.session.commit()
    return result
