from __future__ import annotations

from fastapi import HTTPException, status


class Auth0Error(HTTPException):
    """Raised when Auth0 token validation fails."""

    def __init__(
        self, detail: str, status_code: int = status.HTTP_401_UNAUTHORIZED
    ) -> None:
        super().__init__(status_code=status_code, detail=detail)


__all__ = ["Auth0Error", "HTTPException", "status"]
