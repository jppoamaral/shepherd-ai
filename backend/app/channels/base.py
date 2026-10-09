"""How 1:1 messages leave Shepherd. Telegram is added later behind this seam.

Two kinds of outgoing message, and only two:
* `send`: a message a leader approved (a reminder). Every channel refuses anything else.
* `reply`: the bot's direct answer to something the volunteer just wrote ("Thank you,
  Anna!", one clarifying question). Fixed wording from code; it never starts a new ask.
"""

import uuid
from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class OutgoingMessage:
    """One approved message to one person. Never addressed to a group (rule 5)."""

    message_id: uuid.UUID
    person_id: uuid.UUID
    person_name: str
    channel_identity: str | None
    body: str
    buttons: tuple[str, ...] = ()


@dataclass(frozen=True)
class BotReply:
    """The bot answering one person's own message, in that person's 1:1 chat."""

    person_id: uuid.UUID
    body: str
    buttons: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class SendResult:
    message_id: uuid.UUID
    ok: bool
    error: str | None = None


class ChannelAdapter(Protocol):
    name: str

    def send(self, message: OutgoingMessage) -> SendResult: ...

    def reply(self, reply: BotReply) -> None: ...


def numbered_fallback(buttons: tuple[str, ...]) -> str:
    """For chats without buttons: "Reply 1 = yes, 2 = can't make it." """
    short = {"Yes, I'll be there": "yes", "I can't make it": "can't make it"}
    options = ", ".join(f"{i} = {short.get(b, b.lower())}" for i, b in enumerate(buttons, 1))
    return f"Reply {options}."
