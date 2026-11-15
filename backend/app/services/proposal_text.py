"""Plain-language titles and summaries for the approval queue. Deterministic.

Each proposal type's handler says how its proposals read (`ProposalHandler.describe`).
"""

import uuid

from sqlalchemy.orm import Session

from app.domain.schemas import ProposalOut
from app.services.approval import HANDLERS
from app.services.names import Names, ProposalText


def describe(
    session: Session, church_id: uuid.UUID, proposals: list[ProposalOut]
) -> list[ProposalOut]:
    names = Names(session, church_id)
    return [p.model_copy(update=_text(p, names)) for p in proposals]


def _text(p: ProposalOut, names: Names) -> dict[str, str | int | None]:
    handler = HANDLERS.get(p.type)
    text = (
        handler.describe(names, p)
        if handler is not None and handler.describe is not None
        else ProposalText(title=p.type.replace("_", " ").capitalize())
    )
    shown: dict[str, str | int | None] = {"title": text.title, "summary": text.summary}
    if text.count is not None:
        shown["count"] = text.count
    return shown
