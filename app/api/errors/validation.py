from __future__ import annotations

from typing import Any

from fastapi import status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.domains.tasks.template_catalog import ALLOWED_TEMPLATE_KEYS


def validation_error_handler(_request, exc: RequestValidationError) -> JSONResponse:
    """Normalize FastAPI validation errors with a stable errorCode."""
    raw_errors = exc.errors()
    sanitized: list[dict[str, Any]] = []
    for err in raw_errors:
        item = dict(err)
        ctx = item.get("ctx")
        if ctx:
            item["ctx"] = {k: str(v) for k, v in ctx.items()}
        sanitized.append(item)

    error_code = "VALIDATION_ERROR"
    details: dict[str, Any] | None = None
    for err in sanitized:
        loc = err.get("loc") or ()
        if any(str(part).lower() == "templatekey" for part in loc):
            error_code = "INVALID_TEMPLATE_KEY"
            details = {"allowed": sorted(ALLOWED_TEMPLATE_KEYS)}
            break

    payload: dict[str, Any] = {
        "detail": sanitized,
        "errorCode": error_code,
        "retryable": False,
    }
    if details:
        payload["details"] = details
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=payload,
    )


__all__ = ["validation_error_handler"]
