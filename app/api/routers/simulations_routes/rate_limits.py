from __future__ import annotations

from fastapi import Request

from app.core.auth import rate_limit

INVITE_CREATE_RATE_LIMIT = rate_limit.RateLimitRule(limit=20, window_seconds=60.0)
INVITE_RESEND_RATE_LIMIT = rate_limit.RateLimitRule(limit=10, window_seconds=60.0)


def _invite_create_rule():
    # Allow tests to override the rate limit via the aggregated simulations module.
    from app.api.routers import simulations as sim_routes

    return getattr(sim_routes, "INVITE_CREATE_RATE_LIMIT", INVITE_CREATE_RATE_LIMIT)


def _invite_resend_rule():
    # Allow tests to override the rate limit via the aggregated simulations module.
    from app.api.routers import simulations as sim_routes

    return getattr(sim_routes, "INVITE_RESEND_RATE_LIMIT", INVITE_RESEND_RATE_LIMIT)


def enforce_invite_create_limit(
    request: Request, user_id: int, invite_email: str
) -> None:
    if not rate_limit.rate_limit_enabled():
        return
    key = rate_limit.rate_limit_key(
        "invite_create",
        str(user_id),
        rate_limit.client_id(request),
        rate_limit.hash_value(str(invite_email)),
    )
    rate_limit.limiter.allow(key, _invite_create_rule())


def enforce_invite_resend_limit(
    request: Request, user_id: int, candidate_session_id: int
) -> None:
    if not rate_limit.rate_limit_enabled():
        return
    key = rate_limit.rate_limit_key(
        "invite_resend",
        str(user_id),
        str(candidate_session_id),
        rate_limit.client_id(request),
    )
    rate_limit.limiter.allow(key, _invite_resend_rule())
