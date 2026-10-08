"""How approved 1:1 messages leave Shepherd. Telegram is added later behind this seam."""

import uuid
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class OutgoingMessage:
    """One approved message to one person. Never addressed to a group (rule 5)."""

    message_id: uuid.UUID
    person_name: str
    channel_identity: str | None
    body: str


@dataclass(frozen=True)
class SendResult:
    message_id: uuid.UUID
    ok: bool
    error: str | None = None


class ChannelAdapter(Protocol):
    name: str

    def send(self, message: OutgoingMessage) -> SendResult: ...
