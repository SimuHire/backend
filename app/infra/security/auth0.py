from functools import lru_cache
from typing import Any

import httpx
from fastapi import HTTPException, status
from jose import jwt
from jose.exceptions import JWTError

from app.infra.config import settings


class Auth0Error(HTTPException):
    """Raised when Auth0 token validation fails."""

    def __init__(
        self, detail: str, status_code: int = status.HTTP_401_UNAUTHORIZED
    ) -> None:
        super().__init__(status_code=status_code, detail=detail)


@lru_cache(maxsize=1)
def get_jwks() -> dict[str, Any]:
    """Fetch and cache the JWKS keys from Auth0."""
    response = httpx.get(settings.auth0_jwks_url, timeout=5)
    response.raise_for_status()
    return response.json()


def decode_auth0_token(token: str) -> dict[str, Any]:
    """Validate a JWT from Auth0 and return its claims."""
    try:
        unverified_header = jwt.get_unverified_header(token)
    except JWTError as exc:
        raise Auth0Error("Invalid token header") from exc

    kid = unverified_header.get("kid")
    if kid is None:
        raise Auth0Error("Token header missing kid")

    alg = unverified_header.get("alg")
    allowed_algs = settings.auth0_algorithms
    if not alg or alg not in allowed_algs:
        raise Auth0Error("Invalid token algorithm")

    jwks = get_jwks()
    key: dict[str, Any] | None = None
    for jwk in jwks.get("keys", []):
        if jwk.get("kid") == kid:
            key = jwk
            break

    if key is None:
        raise Auth0Error("Signing key not found")

    try:
        payload = jwt.decode(
            token,
            key,
            algorithms=settings.auth0_algorithms,
            audience=settings.auth0_audience,
            issuer=settings.auth0_issuer,
            options={"verify_at_hash": False},
        )
    except JWTError as exc:
        raise Auth0Error("Invalid token") from exc

    return payload
