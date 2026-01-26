from __future__ import annotations

from .base import EmailMessage


class MemoryEmailProvider:
    """Test helper that captures sent messages in memory."""

    def __init__(self):
        self.sent: list[EmailMessage] = []

    async def send(self, message: EmailMessage) -> str | None:
        self.sent.append(message)
        return f"memory-{len(self.sent)}"
