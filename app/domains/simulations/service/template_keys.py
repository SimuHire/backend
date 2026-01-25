from __future__ import annotations

from fastapi import status

from app.domains.tasks.template_catalog import (
    ALLOWED_TEMPLATE_KEYS,
    DEFAULT_TEMPLATE_KEY,
    TemplateKeyError,
    validate_template_key,
)
from app.infra.errors import ApiError


def resolve_template_key(payload) -> str:
    try:
        return validate_template_key(
            getattr(payload, "templateKey", DEFAULT_TEMPLATE_KEY)
            or DEFAULT_TEMPLATE_KEY
        )
    except TemplateKeyError as exc:
        allowed = sorted(ALLOWED_TEMPLATE_KEYS)
        raise ApiError(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid templateKey. Allowed: " + ", ".join(allowed),
            error_code="INVALID_TEMPLATE_KEY",
            details={"allowed": allowed},
        ) from exc
