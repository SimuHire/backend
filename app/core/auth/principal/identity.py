from __future__ import annotations

from fastapi import HTTPException, status

from app.core.settings import settings

from .email_claims import extract_email
from .selectors import first_claim


def extract_identity(
    claims: dict[str, object],
) -> tuple[str, str, str | None, list[str]]:
    sub = claims.get("sub")
    if not isinstance(sub, str) or not sub:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token"
        )

    email = extract_email(claims)

    name_raw = first_claim(claims, ["name", settings.auth.name_claim], default=None)
    name = name_raw.strip() if isinstance(name_raw, str) and name_raw.strip() else None
    roles_claim = first_claim(
        claims, [settings.auth.AUTH0_ROLES_CLAIM, "roles"], default=[]
    )
    roles = [r for r in roles_claim or [] if isinstance(r, str)]
    return sub, email, name, roles
