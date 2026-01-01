from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

TOKEN_TTL_MINUTES = 60


def hash_token(token: str) -> str:
    """Return a hex digest for the candidate access token."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def mint_token(now: datetime | None = None, ttl_minutes: int = TOKEN_TTL_MINUTES):
    """Generate a new candidate token and metadata."""
    now = now or datetime.now(UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    token = secrets.token_urlsafe(32)
    token_hash = hash_token(token)
    expires_at = now + timedelta(minutes=ttl_minutes)
    return token, token_hash, expires_at, now
