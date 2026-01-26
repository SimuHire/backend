from __future__ import annotations

import logging
from typing import Any

from jose import jwt
from jose.exceptions import ExpiredSignatureError, JWTError

from app.core.settings import settings

from .errors import Auth0Error

logger = logging.getLogger(__name__)


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
    from app.core.auth import auth0

    jwks = auth0.get_jwks()
    key = next((jwk for jwk in jwks.get("keys", []) if jwk.get("kid") == kid), None)
    if key is None:
        auth0.clear_jwks_cache()
        jwks = auth0.get_jwks()
        key = next((jwk for jwk in jwks.get("keys", []) if jwk.get("kid") == kid), None)
        if key is None:
            _log_failure("kid_not_found", kid=kid, alg=alg)
            raise Auth0Error("Signing key not found")
    try:
        return jwt.decode(
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


__all__ = ["decode_auth0_token", "_log_failure"]
