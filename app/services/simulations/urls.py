from __future__ import annotations

from app.core.settings import settings


def invite_url(token: str) -> str:
    """Construct candidate portal URL for an invite token."""
    return f"{settings.CANDIDATE_PORTAL_BASE_URL.rstrip('/')}/candidate/session/{token}"
