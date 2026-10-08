"""Writes to outgoing 1:1 messages.

Only ApprovalService may import this module. Agents must not;
`tests/unit/test_architecture.py` enforces that (architecture rule 1).
"""

import uuid

from sqlalchemy.orm import Session

from app.db.models import Message
from app.domain.enums import MessageStatus


class MessageWriter:
    def __init__(self, session: Session, church_id: uuid.UUID) -> None:
        self.session = session
        self.church_id = church_id

    def create(self, *, person_id: uuid.UUID, channel: str, body: str) -> Message:
        message = Message(
            church_id=self.church_id,
            person_id=person_id,
            channel=channel,
            body=body,
            status=MessageStatus.APPROVED,
        )
        self.session.add(message)
        self.session.flush()
        return message
