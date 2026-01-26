from __future__ import annotations

from fastapi import HTTPException, status

from app.services.tasks.template_catalog import (
    ALLOWED_TEMPLATE_KEYS,
    validate_template_key,
)

MAX_LIVE_TEMPLATE_KEYS = 5


def validate_live_request(payload) -> tuple[list[str], int, int]:
    if payload.mode != "live":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Only live mode is supported for this endpoint",
        )
    if not payload.templateKeys:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="templateKeys is required",
        )
    if len(payload.templateKeys) > MAX_LIVE_TEMPLATE_KEYS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"templateKeys must include {MAX_LIVE_TEMPLATE_KEYS} or fewer items",
        )
    invalid = [key for key in payload.templateKeys if key not in ALLOWED_TEMPLATE_KEYS]
    if invalid:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid templateKeys: {', '.join(invalid)}",
        )
    template_keys = [validate_template_key(key) for key in payload.templateKeys]
    timeout_seconds = max(1, min(payload.timeoutSeconds, 600))
    concurrency = max(1, min(payload.concurrency, 5))
    return template_keys, timeout_seconds, concurrency
