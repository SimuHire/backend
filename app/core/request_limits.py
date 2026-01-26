from __future__ import annotations

from fastapi import status
from fastapi.responses import JSONResponse

from app.core.settings import settings


class RequestTooLarge(Exception):
    pass


class RequestSizeLimitMiddleware:
    def __init__(self, app, max_body_bytes: int | None = None) -> None:
        self.app = app
        self.max_body_bytes = max_body_bytes or settings.MAX_REQUEST_BODY_BYTES

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http" or scope.get("method") not in {
            "POST",
            "PUT",
            "PATCH",
        }:
            await self.app(scope, receive, send)
            return
        headers = dict(scope.get("headers") or [])
        content_length = headers.get(b"content-length", b"").decode("latin1").strip()
        if content_length.isdigit() and int(content_length) > self.max_body_bytes:
            await self._reject(scope, receive, send)
            return
        received = 0

        async def limited_receive():
            nonlocal received
            message = await receive()
            if message.get("type") == "http.request":
                received += len(message.get("body", b"") or b"")
                if received > self.max_body_bytes:
                    raise RequestTooLarge()
            return message

        try:
            await self.app(scope, limited_receive, send)
        except RequestTooLarge:
            await self._reject(scope, receive, send)

    async def _reject(self, scope, receive, send):
        response = JSONResponse(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            content={"detail": "Request body too large"},
        )
        await response(scope, receive, send)


__all__ = ["RequestSizeLimitMiddleware", "RequestTooLarge"]
