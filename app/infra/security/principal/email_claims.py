from __future__ import annotations
import logging
from fastapi import HTTPException, status
from app.infra.config import settings
from .selectors import first_claim, normalize_email

logger = logging.getLogger(__name__)

def configured_email_claim() -> str:
    value = (settings.auth.AUTH0_EMAIL_CLAIM or "").strip()
    if value:
        return value
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="AUTH0_EMAIL_CLAIM not configured")

def extract_email(claims: dict[str, object]) -> str:
    configured = configured_email_claim()
    email = normalize_email(first_claim(claims, [configured, "email", next((k for k in claims if isinstance(k, str) and k.endswith("/email")), None)], default=None))
    if email:
        return email
    try:
        available_claim_keys = sorted([str(k) for k in claims])[:50]
    except Exception:  # pragma: no cover - defensive
        available_claim_keys = []
    logger.debug("email_claim_missing", extra={"expected_email_claim": configured, "available_claim_keys": available_claim_keys})
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

__all__ = ["extract_email", "configured_email_claim"]
