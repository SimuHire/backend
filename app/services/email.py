from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Literal

from app.infra.notifications.email_provider import (
    EmailMessage,
    EmailProvider,
    EmailSendError,
)

EmailStatus = Literal["sent", "failed", "rate_limited"]


@dataclass
class EmailSendResult:
    """Result of attempting to send an email."""

    status: EmailStatus
    message_id: str | None = None
    error: str | None = None


class EmailService:
    """High-level email sender with retry support."""

    def __init__(
        self,
        provider: EmailProvider,
        *,
        sender: str,
        max_attempts: int = 2,
    ):
        self.provider = provider
        self.sender = sender
        self.max_attempts = max(1, max_attempts)

    async def send_email(
        self, *, to: str, subject: str, text: str, html: str | None = None
    ) -> EmailSendResult:
        """Send an email with minimal retry support."""
        last_error: EmailSendError | None = None

        for attempt in range(self.max_attempts):
            try:
                message_id = await self.provider.send(
                    EmailMessage(
                        to=to,
                        subject=subject,
                        text=text,
                        html=html,
                        sender=self.sender,
                    )
                )
                return EmailSendResult(status="sent", message_id=message_id)
            except EmailSendError as exc:
                last_error = exc
                should_retry = exc.retryable and attempt < self.max_attempts - 1
                if not should_retry:
                    break
                # Minimal cooperative backoff without blocking event loop.
                await asyncio.sleep(0.05 * (attempt + 1))

        return EmailSendResult(
            status="failed",
            message_id=None,
            error=str(last_error) if last_error else "Email send failed",
        )
