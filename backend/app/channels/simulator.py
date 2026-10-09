"""The demo stand-in for Telegram: each person's thread, kept for the simulator page.

Stores only Shepherd's side: approved messages and the bot's replies. The volunteer's
own messages stay in the simulator's browser, as they would stay in Telegram.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.channels.base import BotReply, OutgoingMessage, SendResult
from app.db.models import Message, SimulatorMessage
from app.domain.enums import MessageStatus


class SimulatorChannel:
    name = "simulator"

    def __init__(self, session: Session, church_id: uuid.UUID) -> None:
        self.session = session
        self.church_id = church_id

    def send(self, message: OutgoingMessage) -> SendResult:
        """Deliver an approved message. Anything not approved is refused, never shown."""
        status = self.session.scalar(
            select(Message.status).where(
                Message.church_id == self.church_id,
                Message.id == message.message_id,
                Message.person_id == message.person_id,
            )
        )
        if status is not MessageStatus.APPROVED:
            return SendResult(message.message_id, ok=False, error="not an approved message")
        self._store(message.person_id, message.body, message.buttons, message.message_id)
        return SendResult(message.message_id, ok=True)

    def reply(self, reply: BotReply) -> None:
        self._store(reply.person_id, reply.body, reply.buttons, None)

    def _store(
        self,
        person_id: uuid.UUID,
        body: str,
        buttons: tuple[str, ...],
        message_id: uuid.UUID | None,
    ) -> None:
        self.session.add(
            SimulatorMessage(
                church_id=self.church_id,
                person_id=person_id,
                body=body,
                buttons=list(buttons),
                message_id=message_id,
                # The real time, not the transaction's: several rows in one request keep order.
                created_at=datetime.now(UTC),
            )
        )
        self.session.flush()
