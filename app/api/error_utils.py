from __future__ import annotations

from typing import Any

from fastapi import status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.domains.github_native.client import GithubError
from app.infra.errors import ApiError


def api_error_handler(_request, exc: ApiError) -> JSONResponse:
    """Return a consistent JSON shape for ApiError."""
    payload: dict[str, Any] = {"detail": exc.detail, "errorCode": exc.error_code}
    if exc.retryable is not None:
        payload["retryable"] = exc.retryable
    if exc.details:
        payload["details"] = exc.details
    return JSONResponse(
        status_code=exc.status_code, content=payload, headers=exc.headers
    )


def register_error_handlers(app) -> None:
    """Attach ApiError handler to the FastAPI app."""
    app.add_exception_handler(ApiError, api_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)


def map_github_error(exc: GithubError) -> ApiError:
    """Return a safe ApiError for GitHub API failures."""
    code = exc.status_code or 0
    detail = "GitHub unavailable. Please try again."
    error_code = "GITHUB_UNAVAILABLE"
    retryable = False
    if code == 401:
        detail = "GitHub token is invalid or misconfigured."
        error_code = "GITHUB_TOKEN_INVALID"
    elif code == 403:
        detail = "GitHub token missing required permissions."
        error_code = "GITHUB_PERMISSION_DENIED"
    elif code == 404:
        detail = "GitHub repository or workflow not found."
        error_code = "GITHUB_NOT_FOUND"
    elif code == 429:
        detail = "GitHub rate limit exceeded. Please retry later."
        error_code = "GITHUB_RATE_LIMITED"
        retryable = True
    return ApiError(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail=detail,
        error_code=error_code,
        retryable=retryable,
    )


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
        msg = str(err.get("msg") or "").lower()
        loc = err.get("loc") or ()
        if (
            "templatekey" in "".join(str(part).lower() for part in loc)
            and "invalid templatekey" in msg
        ):
            error_code = "INVALID_TEMPLATE_KEY"
            # try to extract allowed list from message text
            text = str(err.get("msg") or "")
            if "Allowed values:" in text:
                allowed_text = text.split("Allowed values:", 1)[1]
                allowed = [
                    part.strip() for part in allowed_text.split(",") if part.strip()
                ]
                details = {"allowed": allowed}
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
