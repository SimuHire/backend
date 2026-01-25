from __future__ import annotations

import logging

import httpx

from .base import EmailSendError

logger = logging.getLogger(__name__)


async def post_json(
    base_url: str,
    path: str,
    payload: dict,
    *,
    provider: str,
    transport: httpx.BaseTransport | None = None,
    headers: dict | None = None,
) -> httpx.Response:
    headers = headers or {}
    try:
        async with httpx.AsyncClient(
            base_url=base_url, timeout=10.0, transport=transport
        ) as client:
            return await client.post(path, json=payload, headers=headers)
    except httpx.HTTPError as exc:  # pragma: no cover - network
        logger.error(
            "email_send_failed", extra={"provider": provider, "error": str(exc)}
        )
        raise EmailSendError("Email provider request failed") from exc


def ensure_success(provider: str, resp: httpx.Response) -> None:
    if resp.status_code < 400:
        return
    logger.error(
        "email_send_failed",
        extra={"provider": provider, "status_code": resp.status_code},
    )
    raise EmailSendError(
        f"Email provider error ({resp.status_code})",
        retryable=resp.status_code >= 500,
    )
