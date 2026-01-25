"""Error handler wiring for FastAPI."""

from app.api.errors.handlers import api_error_handler, register_error_handlers

__all__ = ["register_error_handlers", "api_error_handler"]
