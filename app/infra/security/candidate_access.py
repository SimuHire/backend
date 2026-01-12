from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, status

from app.infra.security.principal import Principal, get_principal


async def require_candidate_principal(
    principal: Annotated[Principal, Depends(get_principal)],
) -> Principal:
    """Require an Auth0 principal with candidate access."""
    if "candidate:access" not in principal.permissions:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Candidate access required",
        )
    return principal
