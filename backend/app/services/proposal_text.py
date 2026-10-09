"""Plain-language titles and summaries for the approval queue. Deterministic."""

import uuid
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Church, Gathering, GatheringType, Ministry, Person, Role
from app.domain.profile import ChurchProfileDraft
from app.domain.schemas import ProposalOut
from app.services.profile import format_time, render_summary


def describe(
    session: Session, church_id: uuid.UUID, proposals: list[ProposalOut]
) -> list[ProposalOut]:
    names = _Names(session, church_id)
    return [p.model_copy(update=_text(p, names)) for p in proposals]


def _text(p: ProposalOut, names: "_Names") -> dict[str, str]:
    payload: dict[str, Any] = p.payload
    if p.type == "church_profile":
        return {
            "title": "Church profile",
            "summary": render_summary(ChurchProfileDraft.model_validate(payload)),
        }
    if p.type == "leader_roster":
        ministry = names.ministry(payload["ministry_id"])
        lines = [
            f"• {names.gathering(a['gathering_id'])} · {names.role(a['role_id'])} · {names.person(a['person_id'])}"
            for a in payload.get("assignments", [])
        ]
        lines += [
            f"• Remember “{n['nickname']}” for {names.person(n['person_id'])}"
            for n in payload.get("nicknames", [])
        ]
        count = len(payload.get("assignments", []))
        return {
            "title": f"{ministry} roster ({count} assignment{'s' if count != 1 else ''})",
            "summary": "\n".join(lines),
        }
    if p.type == "memory":
        ministry = names.ministry(payload["ministry_id"])
        about = (
            f" about {names.person(payload['about_person_id'])}"
            if payload.get("about_person_id")
            else ""
        )
        return {
            "title": f"Should I remember this? ({ministry})",
            "summary": f"“{payload['text']}”{about}",
        }
    if p.type == "reminders":
        messages = payload.get("messages", [])
        n = len(messages)
        return {
            "title": f"{n} reminder{'s' if n != 1 else ''} ready for "
            f"{names.gathering(payload['gathering_id'])}",
            "summary": "\n\n".join(
                f"To {names.person(m['person_id'])}: {m['body']}" for m in messages
            ),
        }
    return {"title": p.type.replace("_", " ").capitalize(), "summary": ""}


class _Names:
    """Church-scoped lookups, cached for one request."""

    def __init__(self, session: Session, church_id: uuid.UUID) -> None:
        self.session, self.church_id = session, church_id
        self.tz = ZoneInfo(session.get_one(Church, church_id).timezone)
        self.cache: dict[tuple[str, str], str] = {}

    def _get(self, kind: str, key: str, query: Any) -> str:
        if (kind, key) not in self.cache:
            self.cache[(kind, key)] = self.session.execute(query).scalar_one_or_none() or "unknown"
        return self.cache[(kind, key)]

    def person(self, pid: str) -> str:
        return self._get(
            "person",
            pid,
            select(Person.name).where(
                Person.church_id == self.church_id, Person.id == uuid.UUID(pid)
            ),
        )

    def ministry(self, mid: str) -> str:
        return self._get(
            "ministry",
            mid,
            select(Ministry.name).where(
                Ministry.church_id == self.church_id, Ministry.id == uuid.UUID(mid)
            ),
        )

    def role(self, rid: str) -> str:
        return self._get(
            "role",
            rid,
            select(Role.name).where(Role.church_id == self.church_id, Role.id == uuid.UUID(rid)),
        )

    def gathering(self, gid: str) -> str:
        if ("gathering", gid) not in self.cache:
            row = self.session.execute(
                select(GatheringType.name, Gathering.start_at)
                .join(Gathering, Gathering.gathering_type_id == GatheringType.id)
                .where(Gathering.church_id == self.church_id, Gathering.id == uuid.UUID(gid))
            ).one_or_none()
            local = row[1].astimezone(self.tz) if row else None
            self.cache[("gathering", gid)] = (
                f"{row[0]}, {local:%a %-d %b} {format_time(local.time())}"
                if row and local
                else "unknown"
            )
        return self.cache[("gathering", gid)]
