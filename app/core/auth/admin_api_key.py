from __future__ import annotations

from typing import Annotated

from fastapi import Header, HTTPException, status

from app.core.settings import settings


def require_admin_key(
    x_admin_key: Annotated[str | None, Header(alias="X-Admin-Key")] = None,
) -> None:
    """Require a valid admin API key header."""
    expected = (settings.ADMIN_API_KEY or "").strip()
    provided = (x_admin_key or "").strip()
    if not expected or not provided or provided != expected:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
