from __future__ import annotations

import logging

from fastapi import status
from fastapi.security import HTTPAuthorizationCredentials

from app.infra.security import auth0

logger = logging.getLogger(__name__)


def decode_credentials(
    credentials: HTTPAuthorizationCredentials, request_id: str | None
) -> dict:
    try:
        return auth0.decode_auth0_token(credentials.credentials)
    except auth0.Auth0Error as exc:
        reason = "invalid_token"
        detail_lower = str(exc.detail).lower()
        if exc.status_code == status.HTTP_503_SERVICE_UNAVAILABLE:
            reason = "jwks_fetch_failed"
        elif detail_lower.startswith("token expired"):
            reason = "expired"
        elif detail_lower.startswith("signing key not found"):
            reason = "kid_not_found"
        logger.warning(
            "auth0_token_invalid",
            extra={"request_id": request_id, "detail": exc.detail, "reason": reason},
        )
        raise
