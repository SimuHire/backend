from __future__ import annotations

import asyncio
import logging
import smtplib
import ssl
from email.message import EmailMessage as StdEmailMessage

from .base import EmailMessage, EmailSendError

logger = logging.getLogger(__name__)


def _build_std_email(message: EmailMessage, sender: str) -> StdEmailMessage:
    email = StdEmailMessage()
    email["Subject"] = message.subject
    email["From"] = message.sender or sender
    email["To"] = message.to
    email.set_content(message.text)
    if message.html:
        email.add_alternative(message.html, subtype="html")
    return email


def _send_sync(email: StdEmailMessage, host: str, port: int, username: str, password: str, use_tls: bool):
    with smtplib.SMTP(host, port, timeout=10) as server:
        server.ehlo()
        if use_tls:
            server.starttls(context=ssl.create_default_context())
        if username:
            server.login(username, password)
        server.send_message(email)


async def send_smtp(
    message: EmailMessage,
    *,
    host: str,
    port: int,
    username: str,
    password: str,
    use_tls: bool,
    sender: str | None,
) -> None:
    email = _build_std_email(message, sender or username)
    try:
        await asyncio.to_thread(_send_sync, email, host, port, username, password, use_tls)
    except Exception as exc:  # pragma: no cover - network
        logger.error("email_send_failed", extra={"provider": "smtp", "error": str(exc)})
        raise EmailSendError("SMTP send failed") from exc
