from __future__ import annotations

from typing import Any

from fastapi import HTTPException


class ApiError(HTTPException):
    """HTTP error with a stable error code and optional metadata."""

    def __init__(
        self,
        *,
        status_code: int,
        detail: str,
        error_code: str,
        retryable: bool | None = None,
        headers: dict[str, Any] | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(status_code=status_code, detail=detail, headers=headers)
        self.error_code = error_code
        self.retryable = retryable
        self.details = details or {}
