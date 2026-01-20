"""Aggregator for candidate session routes split into submodules."""

from app.api.routes.candidate_sessions_routes import router
from app.api.routes.candidate_sessions_routes.current_task import get_current_task
from app.api.routes.candidate_sessions_routes.invites import list_candidate_invites
from app.api.routes.candidate_sessions_routes.resolve import (
    claim_candidate_session,
    resolve_candidate_session,
)
from app.domains.candidate_sessions import service as cs_service

__all__ = [
    "router",
    "cs_service",
    "resolve_candidate_session",
    "claim_candidate_session",
    "get_current_task",
    "list_candidate_invites",
]
