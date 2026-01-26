from __future__ import annotations

import logging

from .base import EmailMessage

logger = logging.getLogger(__name__)


class ConsoleEmailProvider:
    """Local/dev provider that logs metadata without sending."""

    def __init__(self, *, sender: str | None = None):
        self.sender = sender

    async def send(self, message: EmailMessage) -> str | None:
        logger.info(
            "email_console_send",
            extra={
                "to": message.to,
                "subject": message.subject,
                "sender": message.sender or self.sender,
            },
        )
        return "console"
