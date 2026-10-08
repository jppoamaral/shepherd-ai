"""A channel that hands approved messages back to the leader as a list to copy and send."""

from app.channels.base import OutgoingMessage, SendResult


class CopyPasteChannel:
    name = "copy_paste"

    def __init__(self) -> None:
        self.outbox: list[OutgoingMessage] = []

    def send(self, message: OutgoingMessage) -> SendResult:
        self.outbox.append(message)
        return SendResult(message_id=message.message_id, ok=True)

    def render(self) -> str:
        """Plain text, one block per person, ready to paste into a 1:1 chat."""
        return "\n\n".join(f"To {m.person_name}:\n{m.body}" for m in self.outbox)
