from __future__ import annotations

from fastapi.security import HTTPAuthorizationCredentials

from .builder import build_principal
from .model import Principal


def build_dev_principal(credentials: HTTPAuthorizationCredentials) -> Principal | None:
    token = credentials.credentials or ""
    if ":" not in token:
        return None
    prefix, _, email = token.partition(":")
    email = email.strip().lower()
    if not email or prefix not in {"candidate", "recruiter"}:
        return None
    claims = {
        "sub": token,
        "email": email,
        "permissions": [f"{prefix}:access"],
        "roles": [prefix],
        "name": email,
    }
    return build_principal(claims)


__all__ = ["build_dev_principal"]
