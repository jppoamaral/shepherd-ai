"""A channel that hands approved messages back to the leader as a list to copy and send."""

from app.channels.base import BotReply, OutgoingMessage, SendResult, numbered_fallback


class CopyPasteChannel:
    name = "copy_paste"

    def __init__(self) -> None:
        self.outbox: list[OutgoingMessage] = []

    def send(self, message: OutgoingMessage) -> SendResult:
        self.outbox.append(message)
        return SendResult(message_id=message.message_id, ok=True)

    def reply(self, reply: BotReply) -> None:
        """Nothing to do: volunteers can't write back through a pasted message."""

    def render(self) -> str:
        """Plain text, one block per person, ready to paste into a 1:1 chat."""
        return "\n\n".join(
            f"To {m.person_name}:\n{m.body}"
            + (f"\n{numbered_fallback(m.buttons)}" if m.buttons else "")
            for m in self.outbox
        )
