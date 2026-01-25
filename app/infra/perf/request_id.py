from __future__ import annotations

import uuid

from starlette.types import Scope


def request_id_from_scope(scope: Scope) -> str:
    """Return existing X-Request-Id header or generate one."""
    headers = scope.get("headers") or []
    for key, value in headers:
        if key.lower() == b"x-request-id":
            try:
                return value.decode()
            except Exception:
                break
    return str(uuid.uuid4())


__all__ = ["request_id_from_scope"]
