from __future__ import annotations

from typing import Any

from fastapi.responses import JSONResponse

from app.infra.errors import ApiError


def api_error_handler(_request, exc: ApiError) -> JSONResponse:
    payload: dict[str, Any] = {"detail": exc.detail, "errorCode": exc.error_code}
    if exc.retryable is not None:
        payload["retryable"] = exc.retryable
    if exc.details:
        payload["details"] = exc.details
    return JSONResponse(
        status_code=exc.status_code, content=payload, headers=exc.headers
    )


__all__ = ["api_error_handler"]
