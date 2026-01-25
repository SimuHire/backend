from app.infra.security import rate_limit

CANDIDATE_CLAIM_RATE_LIMIT = rate_limit.RateLimitRule(limit=10, window_seconds=60.0)
CANDIDATE_CURRENT_TASK_RATE_LIMIT = rate_limit.RateLimitRule(
    limit=60, window_seconds=60.0
)
CANDIDATE_INVITES_RATE_LIMIT = rate_limit.RateLimitRule(limit=30, window_seconds=60.0)


def _claim_rule():
    # Allow tests to override the rate limit via the aggregated candidate routes module.
    from app.api.routes import candidate_sessions as candidate_routes

    return getattr(
        candidate_routes, "CANDIDATE_CLAIM_RATE_LIMIT", CANDIDATE_CLAIM_RATE_LIMIT
    )


def rate_limit_claim(request, token: str) -> None:
    if not rate_limit.rate_limit_enabled():
        return
    key = rate_limit.rate_limit_key(
        "candidate_claim",
        rate_limit.client_id(request),
        rate_limit.hash_value(token),
    )
    rate_limit.limiter.allow(key, _claim_rule())
