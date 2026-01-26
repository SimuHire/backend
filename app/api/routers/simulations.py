"""Aggregator for simulation routes split into submodules."""

from app.api.routers.simulations_routes import rate_limits, router
from app.api.routers.simulations_routes.candidates import list_simulation_candidates
from app.api.routers.simulations_routes.create import create_simulation
from app.api.routers.simulations_routes.detail import get_simulation_detail
from app.api.routers.simulations_routes.invite_create import create_candidate_invite
from app.api.routers.simulations_routes.invite_resend import resend_candidate_invite
from app.api.routers.simulations_routes.list_simulations import list_simulations
from app.core.auth.roles import ensure_recruiter_or_none
from app.domains.notifications import service as notification_service
from app.domains.simulations import service as sim_service
from app.domains.submissions import service_candidate as submission_service

INVITE_CREATE_RATE_LIMIT = rate_limits.INVITE_CREATE_RATE_LIMIT
INVITE_RESEND_RATE_LIMIT = rate_limits.INVITE_RESEND_RATE_LIMIT
rate_limit = rate_limits.rate_limit

__all__ = [
    "router",
    "create_candidate_invite",
    "resend_candidate_invite",
    "create_simulation",
    "get_simulation_detail",
    "list_simulation_candidates",
    "list_simulations",
    "notification_service",
    "submission_service",
    "sim_service",
    "ensure_recruiter_or_none",
    "rate_limit",
    "INVITE_CREATE_RATE_LIMIT",
    "INVITE_RESEND_RATE_LIMIT",
]
