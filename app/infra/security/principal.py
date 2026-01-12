from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Annotated, Any

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.infra.config import settings
from app.infra.security import auth0

bearer_scheme = HTTPBearer(auto_error=False)
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Principal:
    """Authenticated principal derived from an Auth0 access token."""

    sub: str
    email: str
    name: str | None
    roles: list[str]
    permissions: list[str]
    claims: dict[str, Any] = field(repr=False)


def _first_claim(
    claims: dict[str, Any], keys: Iterable[str], *, default: Any | None = None
) -> Any | None:
    for key in keys:
        if not key:
            continue
        if key in claims:
            return claims[key]
    return default


def _normalize_email(value: str | None) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip().lower()


def _extract_principal(claims: dict[str, Any]) -> Principal:
    sub = claims.get("sub")
    if not isinstance(sub, str) or not sub:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token"
        )

    configured_email_claim = (settings.auth.AUTH0_EMAIL_CLAIM or "").strip()
    if not configured_email_claim:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="AUTH0_EMAIL_CLAIM not configured",
        )

    email = _normalize_email(
        _first_claim(
            claims,
            [
                configured_email_claim,
                "email",
                next(
                    (k for k in claims if isinstance(k, str) and k.endswith("/email")),
                    None,
                ),
            ],
            default=None,
        )
    )
    if not email:
        try:
            available_claim_keys = sorted([str(k) for k in claims])[:50]
        except Exception:  # pragma: no cover - defensive
            available_claim_keys = []
        logger.debug(
            "email_claim_missing",
            extra={
                "expected_email_claim": configured_email_claim,
                "available_claim_keys": available_claim_keys,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token"
        )

    name_raw = _first_claim(claims, ["name", settings.auth.name_claim], default=None)
    name = name_raw.strip() if isinstance(name_raw, str) and name_raw.strip() else None
    roles_claim = _first_claim(
        claims, [settings.auth.AUTH0_ROLES_CLAIM, "roles"], default=[]
    )
    roles = [r for r in roles_claim or [] if isinstance(r, str)]

    permissions_claim = claims.get("permissions")
    if not isinstance(permissions_claim, list):
        permissions_claim = claims.get(settings.auth.AUTH0_PERMISSIONS_CLAIM) or []
    permissions = [p for p in permissions_claim if isinstance(p, str)]
    if not permissions:
        perm_str = claims.get(settings.auth.permissions_str_claim)
        if isinstance(perm_str, str) and perm_str.strip():
            permissions = [
                p.strip() for p in perm_str.replace(",", " ").split() if p.strip()
            ]
    if not permissions and roles:
        lowered = [r.lower() for r in roles]
        if any("recruiter" in r for r in lowered):
            permissions.append("recruiter:access")
        if any("candidate" in r for r in lowered):
            permissions.append("candidate:access")

    return Principal(
        sub=sub,
        email=email,
        name=name or email.split("@")[0],
        roles=roles,
        permissions=permissions,
        claims=claims,
    )


async def get_principal(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    request: Request,
) -> Principal:
    """Decode Auth0 JWT and build a typed principal."""
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    request_id = (
        request.headers.get("x-request-id")
        or request.headers.get("x-correlation-id")
        or ""
    ).strip() or None

    try:
        claims = auth0.decode_auth0_token(credentials.credentials)
    except auth0.Auth0Error as exc:
        reason = "invalid_token"
        if exc.status_code == status.HTTP_503_SERVICE_UNAVAILABLE:
            reason = "jwks_fetch_failed"
        elif str(exc.detail).lower().startswith("token expired"):
            reason = "expired"
        elif str(exc.detail).lower().startswith("signing key not found"):
            reason = "kid_not_found"
        logger.warning(
            "auth0_token_invalid",
            extra={"request_id": request_id, "detail": exc.detail, "reason": reason},
        )
        raise

    try:
        return _extract_principal(claims)
    except HTTPException as exc:
        logger.warning(
            "auth0_claims_invalid",
            extra={
                "request_id": request_id,
                "detail": exc.detail,
                "reason": "claims_invalid",
            },
        )
        raise


def require_permissions(required: list[str]):
    """Dependency factory enforcing that the principal has all required permissions."""

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
