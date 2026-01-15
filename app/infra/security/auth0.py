import atexit
import logging
import threading
import time
from typing import Any

import httpx
from fastapi import HTTPException, status
from jose import jwt
from jose.exceptions import ExpiredSignatureError, JWTError

from app.infra.config import settings

logger = logging.getLogger(__name__)
_http_client = httpx.Client(timeout=5)
_jwks_cache: dict[str, Any] = {"fetched_at": 0.0, "jwks": None}
_jwks_lock = threading.Lock()


def _close_http_client() -> None:
    _http_client.close()


atexit.register(_close_http_client)


class Auth0Error(HTTPException):
    """Raised when Auth0 token validation fails."""

    def __init__(
        self, detail: str, status_code: int = status.HTTP_401_UNAUTHORIZED
    ) -> None:
        super().__init__(status_code=status_code, detail=detail)


def _fetch_jwks() -> dict[str, Any]:
    """Fetch JWKS keys from Auth0."""
    response = _http_client.get(settings.auth.jwks_url)
    response.raise_for_status()
    return response.json()


def get_jwks() -> dict[str, Any]:
    """Fetch and cache the JWKS keys from Auth0."""
    now = time.time()
    cached = _jwks_cache.get("jwks")
    ttl = settings.auth.AUTH0_JWKS_CACHE_TTL_SECONDS
    fetched_at = float(_jwks_cache.get("fetched_at") or 0.0)
    if cached is not None and now - fetched_at <= ttl:
        return cached
    try:
        with _jwks_lock:
            now = time.time()
            cached = _jwks_cache.get("jwks")
            fetched_at = float(_jwks_cache.get("fetched_at") or 0.0)
            if cached is not None and now - fetched_at <= ttl:
                return cached
            jwks = _fetch_jwks()
            _jwks_cache["jwks"] = jwks
            _jwks_cache["fetched_at"] = now
            return jwks
    except httpx.HTTPError as exc:
        logger.warning(
            "auth0_jwks_fetch_failed",
            extra={"jwks_url": settings.auth.jwks_url, "reason": "jwks_fetch_failed"},
        )
        raise Auth0Error(
            "Auth provider unavailable", status_code=status.HTTP_503_SERVICE_UNAVAILABLE
        ) from exc


def clear_jwks_cache() -> None:
    """Reset the in-memory JWKS cache."""
    with _jwks_lock:
        _jwks_cache["jwks"] = None
        _jwks_cache["fetched_at"] = 0.0


def _log_failure(reason: str, *, kid: str | None, alg: str | None) -> None:
    logger.warning(
        "auth0_token_validation_failed",
        extra={
            "reason": reason,
            "kid": kid,
            "alg": alg,
            "iss": settings.auth.issuer,
            "aud": settings.auth.audience,
        },
    )


def decode_auth0_token(token: str) -> dict[str, Any]:
    """Validate a JWT from Auth0 and return its claims."""
    try:
        unverified_header = jwt.get_unverified_header(token)
    except JWTError as exc:
        _log_failure("invalid_token_header", kid=None, alg=None)
        raise Auth0Error("Invalid token header") from exc

    kid = unverified_header.get("kid")
    if kid is None:
        _log_failure("kid_missing", kid=None, alg=unverified_header.get("alg"))
        raise Auth0Error("Token header missing kid")

    alg = unverified_header.get("alg")
    allowed_algs = settings.auth.algorithms
    if not alg or alg not in allowed_algs:
        _log_failure("invalid_algorithm", kid=kid, alg=alg)
        raise Auth0Error("Invalid token algorithm")

    jwks = get_jwks()
    key: dict[str, Any] | None = None
    for jwk in jwks.get("keys", []):
        if jwk.get("kid") == kid:
            key = jwk
            break

    if key is None:
        clear_jwks_cache()
        jwks = get_jwks()
        for jwk in jwks.get("keys", []):
            if jwk.get("kid") == kid:
                key = jwk
                break
        if key is None:
            _log_failure("kid_not_found", kid=kid, alg=alg)
            raise Auth0Error("Signing key not found")

    try:
        payload = jwt.decode(
            token,
            key,
            algorithms=settings.auth.algorithms,
            audience=settings.auth.audience,
            issuer=settings.auth.issuer,
            options={
                "verify_at_hash": False,
                "leeway": settings.auth.AUTH0_LEEWAY_SECONDS,
            },
        )
    except ExpiredSignatureError as exc:
        _log_failure("expired", kid=kid, alg=alg)
        raise Auth0Error("Token expired") from exc
    except JWTError as exc:
        _log_failure("invalid_token", kid=kid, alg=alg)
        raise Auth0Error("Invalid token") from exc

    return payload
