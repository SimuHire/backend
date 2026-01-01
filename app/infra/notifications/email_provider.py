from __future__ import annotations

import asyncio
import logging
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage as StdEmailMessage
from typing import Protocol

import httpx

logger = logging.getLogger(__name__)


def _parse_sender(value: str) -> tuple[str, str | None]:
    """Split 'Name <email@x>' into (email, name)."""
    if not value:
        return "", None
    text = value.strip()
    if "<" in text and ">" in text:
        name_part, _, rest = text.partition("<")
        email = rest.split(">", 1)[0].strip()
        name = name_part.strip().strip('"') or None
        return email, name
    return text, None


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
        """Send an email message and return provider message id if available."""


class ConsoleEmailProvider:
    """Local/dev provider that logs metadata without sending."""

    def __init__(self, *, sender: str | None = None):
        self.sender = sender

    async def send(self, message: EmailMessage) -> str | None:
        """Log email metadata instead of sending."""
        logger.info(
            "email_console_send",
            extra={
                "to": message.to,
                "subject": message.subject,
                "sender": message.sender or self.sender,
            },
        )
        return "console"


class MemoryEmailProvider:
    """Test helper that captures sent messages in memory."""

    def __init__(self):
        self.sent: list[EmailMessage] = []

    async def send(self, message: EmailMessage) -> str | None:
        """Capture message for assertions."""
        self.sent.append(message)
        return f"memory-{len(self.sent)}"


class ResendEmailProvider:
    """HTTP-based provider for Resend."""

    def __init__(
        self,
        api_key: str,
        *,
        sender: str,
        transport: httpx.BaseTransport | None = None,
    ):
        """Instantiate a Resend provider."""
        if not api_key:
            raise ValueError("RESEND_API_KEY is required for Resend provider")
        self.api_key = api_key
        self.sender = sender
        self.transport = transport

    async def send(self, message: EmailMessage) -> str | None:
        """Send via Resend API."""
        payload = {
            "from": message.sender or self.sender,
            "to": [message.to],
            "subject": message.subject,
            "text": message.text,
        }
        if message.html:
            payload["html"] = message.html

        try:
            async with httpx.AsyncClient(
                base_url="https://api.resend.com",
                timeout=10.0,
                transport=self.transport,
            ) as client:
                resp = await client.post(
                    "/emails",
                    json=payload,
                    headers={"Authorization": f"Bearer {self.api_key}"},
                )
        except httpx.HTTPError as exc:  # pragma: no cover - network
            logger.error(
                "email_send_failed",
                extra={"provider": "resend", "error": str(exc)},
            )
            raise EmailSendError("Email provider request failed") from exc

        if resp.status_code >= 400:
            logger.error(
                "email_send_failed",
                extra={
                    "provider": "resend",
                    "status_code": resp.status_code,
                },
            )
            retryable = resp.status_code >= 500
            raise EmailSendError(
                f"Email provider error ({resp.status_code})", retryable=retryable
            )

        try:
            data = resp.json()
        except ValueError:
            data = {}
        message_id = data.get("id") or data.get("message") or None
        return str(message_id) if message_id else None


class SendGridEmailProvider:
    """HTTP-based provider for SendGrid."""

    def __init__(
        self,
        api_key: str,
        *,
        sender: str,
        transport: httpx.BaseTransport | None = None,
    ):
        """Instantiate a SendGrid provider."""
        if not api_key:
            raise ValueError("SENDGRID_API_KEY is required for SendGrid provider")
        self.api_key = api_key
        self.sender = sender
        self.transport = transport

    async def send(self, message: EmailMessage) -> str | None:
        """Send via SendGrid v3 API."""
        from_email, from_name = _parse_sender(message.sender or self.sender)
        from_obj = {"email": from_email}
        if from_name:
            from_obj["name"] = from_name
        payload = {
            "personalizations": [{"to": [{"email": message.to}]}],
            "from": from_obj,
            "subject": message.subject,
            "content": [
                {"type": "text/plain", "value": message.text},
            ],
        }
        if message.html:
            payload["content"].append({"type": "text/html", "value": message.html})

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        try:
            async with httpx.AsyncClient(
                base_url="https://api.sendgrid.com",
                timeout=10.0,
                transport=self.transport,
            ) as client:
                resp = await client.post("/v3/mail/send", json=payload, headers=headers)
        except httpx.HTTPError as exc:  # pragma: no cover - network
            logger.error(
                "email_send_failed",
                extra={"provider": "sendgrid", "error": str(exc)},
            )
            raise EmailSendError("Email provider request failed") from exc

        if resp.status_code >= 400:
            logger.error(
                "email_send_failed",
                extra={
                    "provider": "sendgrid",
                    "status_code": resp.status_code,
                },
            )
            retryable = resp.status_code >= 500
            raise EmailSendError(
                f"Email provider error ({resp.status_code})", retryable=retryable
            )
        return resp.headers.get("X-Message-Id") or None


class SMTPEmailProvider:
    """SMTP provider using the standard library."""

    def __init__(
        self,
        host: str,
        port: int = 587,
        *,
        username: str | None = None,
        password: str | None = None,
        use_tls: bool = True,
        sender: str | None = None,
    ):
        """Instantiate SMTP provider."""
        if not host:
            raise ValueError("SMTP_HOST is required for SMTP provider")
        self.host = host
        self.port = port
        self.username = username or ""
        self.password = password or ""
        self.use_tls = use_tls
        self.sender = sender

    async def send(self, message: EmailMessage) -> str | None:
        """Send via SMTP with optional TLS and auth."""
        email = StdEmailMessage()
        email["Subject"] = message.subject
        email["From"] = message.sender or self.sender or self.username
        email["To"] = message.to
        email.set_content(message.text)
        if message.html:
            email.add_alternative(message.html, subtype="html")

        def _send_sync():
            with smtplib.SMTP(self.host, self.port, timeout=10) as server:
                server.ehlo()
                if self.use_tls:
                    context = ssl.create_default_context()
                    server.starttls(context=context)
                if self.username:
                    server.login(self.username, self.password)
                server.send_message(email)

        try:
            await asyncio.to_thread(_send_sync)
        except Exception as exc:  # pragma: no cover - network
            logger.error(
                "email_send_failed",
                extra={"provider": "smtp", "error": str(exc)},
            )
            raise EmailSendError("SMTP send failed") from exc
        return None
