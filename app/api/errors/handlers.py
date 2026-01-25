from __future__ import annotations

from fastapi.exceptions import RequestValidationError

from app.api.errors.response import api_error_handler
from app.api.errors.validation import validation_error_handler
from app.infra.errors import ApiError


def register_error_handlers(app) -> None:
    app.add_exception_handler(ApiError, api_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)


__all__ = ["api_error_handler", "register_error_handlers"]
