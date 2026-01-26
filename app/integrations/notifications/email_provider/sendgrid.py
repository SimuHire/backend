from __future__ import annotations

import logging

from .base import EmailMessage
from .helpers import parse_sender
from .http import ensure_success, post_json

logger = logging.getLogger(__name__)


class SendGridEmailProvider:
    """HTTP-based provider for SendGrid."""

    def __init__(self, api_key: str, *, sender: str, transport=None):
        if not api_key:
            raise ValueError("SENDGRID_API_KEY is required for SendGrid provider")
        self.api_key = api_key
        self.sender = sender
        self.transport = transport

    async def send(self, message: EmailMessage) -> str | None:
        from_email, from_name = parse_sender(message.sender or self.sender)
        from_obj = {"email": from_email}
        if from_name:
            from_obj["name"] = from_name
        payload = {
            "personalizations": [{"to": [{"email": message.to}]}],
            "from": from_obj,
            "subject": message.subject,
            "content": [{"type": "text/plain", "value": message.text}],
        }
        if message.html:
            payload["content"].append({"type": "text/html", "value": message.html})

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        resp = await post_json(
            "https://api.sendgrid.com",
            "/v3/mail/send",
            payload,
            provider="sendgrid",
            transport=self.transport,
            headers=headers,
        )
        ensure_success("sendgrid", resp)
        return resp.headers.get("X-Message-Id") or None
