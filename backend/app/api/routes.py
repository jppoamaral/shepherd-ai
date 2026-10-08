"""Read-only endpoints and shared API dependencies. Scoped to one church under /churches/{church_id}.

No auth yet (synthetic data, local only). Auth must land before any real church data.
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.db.models import Church
from app.db.repositories.reads import ChurchReader, list_churches
from app.db.session import get_session
from app.domain.schemas import ChurchOut, GatheringOut, GatheringTypeOut, MinistryOut, PersonOut

router = APIRouter()
SessionDep = Annotated[Session, Depends(get_session)]


@router.get("/health")
def health(session: SessionDep, response: Response) -> dict[str, str]:
    try:
        session.execute(text("SELECT 1"))
    except Exception:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "degraded", "database": "unreachable"}
    return {"status": "ok", "database": "ok"}


def church_reader(church_id: uuid.UUID, session: SessionDep) -> ChurchReader:
    if session.scalar(select(Church.id).where(Church.id == church_id)) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "church not found")
    return ChurchReader(session, church_id)


ReaderDep = Annotated[ChurchReader, Depends(church_reader)]


@router.get("/churches")
def get_churches(session: SessionDep) -> list[ChurchOut]:
    return list_churches(session)


@router.get("/churches/{church_id}")
def get_church(reader: ReaderDep) -> ChurchOut:
    return reader.church()


@router.get("/churches/{church_id}/ministries")
def get_ministries(reader: ReaderDep) -> list[MinistryOut]:
    return reader.ministries()


@router.get("/churches/{church_id}/people")
def get_people(reader: ReaderDep) -> list[PersonOut]:
    return reader.people()


@router.get("/churches/{church_id}/gathering-types")
def get_gathering_types(reader: ReaderDep) -> list[GatheringTypeOut]:
    return reader.gathering_types()


@router.get("/churches/{church_id}/gatherings")
def get_gatherings(
    reader: ReaderDep,
    start: Annotated[datetime | None, Query(alias="from")] = None,
    end: Annotated[datetime | None, Query(alias="to")] = None,
) -> list[GatheringOut]:
    """Gatherings starting in [from, to). Defaults to the next four weeks."""
    start = _aware(start) if start else datetime.now(UTC)
    end = _aware(end) if end else start + timedelta(weeks=4)
    if end <= start:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "'to' must be after 'from'")
    return reader.gatherings(start, end)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)
