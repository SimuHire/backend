from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, status

from .dependencies import get_principal
from .model import Principal


def require_permissions(required: list[str]):
    """Dependency enforcing that the principal has all required permissions."""

    async def _dependency(
        principal: Annotated[Principal, Depends(get_principal)],
    ) -> Principal:
        missing = [p for p in required if p not in principal.permissions]
        if missing:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return principal

    return _dependency
