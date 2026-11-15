"""Names for ids, for plain-language text. Church-scoped and cached for one request."""

import uuid
from dataclasses import dataclass
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Church, Gathering, GatheringType, Ministry, Person, Role
from app.services.profile import format_time


@dataclass(frozen=True)
class ProposalText:
    """How a proposal reads in the approval queue."""

    title: str
    summary: str = ""
    # Reminders: how many will actually be sent.
    count: int | None = None


class Names:
    def __init__(self, session: Session, church_id: uuid.UUID) -> None:
        self.session, self.church_id = session, church_id
        self.tz = ZoneInfo(session.get_one(Church, church_id).timezone)
        self.cache: dict[tuple[str, uuid.UUID], str] = {}

    def _get(self, kind: str, key: uuid.UUID, query: Any) -> str:
        if (kind, key) not in self.cache:
            self.cache[(kind, key)] = self.session.execute(query).scalar_one_or_none() or "unknown"
        return self.cache[(kind, key)]

    def person(self, pid: uuid.UUID) -> str:
        return self._get(
            "person",
            pid,
            select(Person.name).where(Person.church_id == self.church_id, Person.id == pid),
        )

    def ministry(self, mid: uuid.UUID) -> str:
        return self._get(
            "ministry",
            mid,
            select(Ministry.name).where(Ministry.church_id == self.church_id, Ministry.id == mid),
        )

    def role(self, rid: uuid.UUID) -> str:
        return self._get(
            "role", rid, select(Role.name).where(Role.church_id == self.church_id, Role.id == rid)
        )

    def gathering(self, gid: uuid.UUID) -> str:
        if ("gathering", gid) not in self.cache:
            row = self.session.execute(
                select(GatheringType.name, Gathering.start_at)
                .join(Gathering, Gathering.gathering_type_id == GatheringType.id)
                .where(Gathering.church_id == self.church_id, Gathering.id == gid)
            ).one_or_none()
            local = row[1].astimezone(self.tz) if row else None
            self.cache[("gathering", gid)] = (
                f"{row[0]}, {local:%a %-d %b} {format_time(local.time())}"
                if row and local
                else "unknown"
            )
        return self.cache[("gathering", gid)]
