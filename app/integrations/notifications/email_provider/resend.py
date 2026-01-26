from __future__ import annotations

import logging

from .base import EmailMessage
from .http import ensure_success, post_json

logger = logging.getLogger(__name__)


class ResendEmailProvider:
    """HTTP-based provider for Resend."""

    def __init__(self, api_key: str, *, sender: str, transport=None):
        if not api_key:
            raise ValueError("TENON_RESEND_API_KEY is required for Resend provider")
        self.api_key = api_key
        self.sender = sender
        self.transport = transport

    async def send(self, message: EmailMessage) -> str | None:
        payload = {
            "from": message.sender or self.sender,
            "to": [message.to],
            "subject": message.subject,
            "text": message.text,
        }
        if message.html:
            payload["html"] = message.html

        resp = await post_json(
            "https://api.resend.com",
            "/emails",
            payload,
            provider="resend",
            transport=self.transport,
            headers={"Authorization": f"Bearer {self.api_key}"},
        )
        ensure_success("resend", resp)
        try:
            data = resp.json()
        except ValueError:
            data = {}
        message_id = data.get("id") or data.get("message") or None
        return str(message_id) if message_id else None
