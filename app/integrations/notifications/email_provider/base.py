from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass
class EmailMessage:
    """Normalized email payload for providers."""

    to: str
    subject: str
    text: str
    html: str | None = None
    sender: str | None = None


class EmailSendError(Exception):
    """Raised when an email provider fails to send."""

    def __init__(self, message: str, *, retryable: bool = True):
        super().__init__(message)
        self.retryable = retryable


class EmailProvider(Protocol):
    """Protocol implemented by email providers."""

    async def send(
        self, message: EmailMessage
    ) -> str | None:  # pragma: no cover - protocol
        ...
