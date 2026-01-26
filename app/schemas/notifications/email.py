from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

EmailStatus = Literal["sent", "failed", "rate_limited"]


@dataclass
class EmailSendResult:
    """Result of attempting to send an email."""

    status: EmailStatus
    message_id: str | None = None
    error: str | None = None


__all__ = ["EmailStatus", "EmailSendResult"]
