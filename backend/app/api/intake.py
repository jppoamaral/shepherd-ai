"""Schedule intake: a scheduler pastes their roster; Shepherd asks about anything unclear."""

import uuid
from collections.abc import Callable
from dataclasses import asdict
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.agents.steward import (
    IntakeClosed,
    IntakeNotAllowed,
    IntakeNotFound,
    IntakeUnreadable,
    IntakeView,
    StewardAgent,
)
from app.api.onboarding import LLMDep
from app.api.routes import ReaderDep
from app.db.repositories.reads import ChurchReader
from app.domain.schemas import IntakeAnswer, IntakeOut, IntakeSubmit
from app.services.intake import IntakeAnswerError

router = APIRouter(tags=["intake"])


def today_dependency() -> date | None:
    """The church's date for resolving schedules; None means "now". Tests pin it."""
    return None


TodayDep = Annotated[date | None, Depends(today_dependency)]


@router.post(
    "/churches/{church_id}/ministries/{ministry_id}/intake", status_code=status.HTTP_201_CREATED
)
def submit_schedule(
    reader: ReaderDep, ministry_id: uuid.UUID, body: IntakeSubmit, llm: LLMDep, today: TodayDep
) -> IntakeOut:
    """Paste a roster in any format. Returns what Shepherd understood and its questions."""
    steward = StewardAgent(reader.session, reader.church_id, llm, today)
    return _run(reader, lambda: steward.intake_schedule(ministry_id, body.person_id, body.text))


@router.get("/churches/{church_id}/intake/{intake_id}")
def get_intake(reader: ReaderDep, intake_id: uuid.UUID, llm: LLMDep) -> IntakeOut:
    steward = StewardAgent(reader.session, reader.church_id, llm)
    return _run(reader, lambda: steward.view(intake_id), commit=False)


@router.post("/churches/{church_id}/intake/{intake_id}/answers")
def answer_question(
    reader: ReaderDep, intake_id: uuid.UUID, body: IntakeAnswer, llm: LLMDep
) -> IntakeOut:
    """Answer one question by picking one of its choices."""
    steward = StewardAgent(reader.session, reader.church_id, llm)
    return _run(
        reader, lambda: steward.answer(intake_id, body.person_id, body.question_id, body.choice_id)
    )


def _run(reader: ChurchReader, action: Callable[[], IntakeView], commit: bool = True) -> IntakeOut:
    try:
        view = action()
    except IntakeNotFound as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error
    except IntakeNotAllowed as error:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(error)) from error
    except IntakeClosed as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
    except (IntakeUnreadable, IntakeAnswerError) as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from error
    if commit:
        reader.session.commit()
    return IntakeOut(**asdict(view))
