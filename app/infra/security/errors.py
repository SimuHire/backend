from __future__ import annotations

from fastapi import status


class AuthError(Exception):
    """Lightweight auth error with HTTP status metadata."""

    def __init__(self, detail: str, *, status_code: int = status.HTTP_401_UNAUTHORIZED):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail
