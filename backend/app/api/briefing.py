"""A leader's weekly briefing and a ministry's roster, with the checks applied."""

import uuid
from datetime import date, timedelta
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from app.api.routes import ReaderDep
from app.domain.schemas import BriefingOut, LeaderSummary, RosterOut
from app.services.briefing import NotALeader, briefing, church_today, leaders, roster

router = APIRouter(tags=["briefing"])
StartQuery = Annotated[date | None, Query(description="Church-local date; defaults to today")]


@router.get("/churches/{church_id}/leaders")
def list_leaders(reader: ReaderDep) -> list[LeaderSummary]:
    """Everyone who schedules or approves, with their ministries (the demo's "who am I")."""
    return leaders(reader.session, reader.church_id)


@router.get("/churches/{church_id}/leaders/{person_id}/briefing")
def get_briefing(reader: ReaderDep, person_id: uuid.UUID, start: StartQuery = None) -> BriefingOut:
    """The next 7 days for this leader: their warnings and their ministries' gatherings."""
    session = reader.session
    try:
        result = briefing(
            session, reader.church_id, person_id, start or church_today(session, reader.church_id)
        )
    except NotALeader as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error
    session.commit()  # findings are kept current as checks run
    return result


@router.get("/churches/{church_id}/ministries/{ministry_id}/roster")
def get_roster(
    reader: ReaderDep,
    ministry_id: uuid.UUID,
    start: StartQuery = None,
    end: Annotated[
        date | None, Query(description="Exclusive; defaults to 4 weeks after start")
    ] = None,
) -> RosterOut:
    session = reader.session
    start = start or church_today(session, reader.church_id)
    result = roster(
        session, reader.church_id, ministry_id, start, end or start + timedelta(weeks=4)
    )
    if result is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ministry not found")
    session.commit()
    return result
