"""Aggregator for candidate session routes split into submodules."""

from app.api.routers.candidate_sessions_routes import rate_limits, router
from app.api.routers.candidate_sessions_routes.current_task import get_current_task
from app.api.routers.candidate_sessions_routes.invites import list_candidate_invites
from app.api.routers.candidate_sessions_routes.resolve import (
    claim_candidate_session,
    resolve_candidate_session,
)
from app.domains.candidate_sessions import service as cs_service

CANDIDATE_CLAIM_RATE_LIMIT = rate_limits.CANDIDATE_CLAIM_RATE_LIMIT
rate_limit = rate_limits.rate_limit

__all__ = [
    "router",
    "cs_service",
    "resolve_candidate_session",
    "claim_candidate_session",
    "get_current_task",
    "list_candidate_invites",
    "rate_limit",
    "CANDIDATE_CLAIM_RATE_LIMIT",
]
