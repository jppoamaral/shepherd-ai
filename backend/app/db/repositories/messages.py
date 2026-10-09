"""Writes to outgoing 1:1 messages.

Only ApprovalService may import this module. Agents must not;
`tests/unit/test_architecture.py` enforces that (architecture rule 1).
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.db.models import Message
from app.domain.enums import MessageStatus


class MessageWriter:
    def __init__(self, session: Session, church_id: uuid.UUID) -> None:
        self.session = session
        self.church_id = church_id

    def create(
        self,
        *,
        person_id: uuid.UUID,
        channel: str,
        body: str,
        kind: str = "message",
        assignment_id: uuid.UUID | None = None,
        gathering_id: uuid.UUID | None = None,
        role_id: uuid.UUID | None = None,
        buttons: list[str] | None = None,
    ) -> Message:
        message = Message(
            church_id=self.church_id,
            person_id=person_id,
            channel=channel,
            body=body,
            status=MessageStatus.APPROVED,
            kind=kind,
            assignment_id=assignment_id,
            gathering_id=gathering_id,
            role_id=role_id,
            buttons=buttons or [],
        )
        self.session.add(message)
        self.session.flush()
        return message

    def mark(self, message: Message, *, ok: bool, error: str | None = None) -> None:
        message.status = MessageStatus.SENT if ok else MessageStatus.FAILED
        message.sent_at = datetime.now(UTC) if ok else None
        message.error = error
        self.session.flush()

    def answered(self, message: Message) -> None:
        """The person answered this ask; a later "1" or "2" no longer counts for it."""
        message.answered_at = datetime.now(UTC)
        self.session.flush()
