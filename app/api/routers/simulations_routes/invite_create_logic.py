from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.error_utils import map_github_error
from app.api.routers.simulations_routes.invite_render import (
    render_invite_error,
    render_invite_response,
)
from app.api.routers.simulations_routes.rate_limits import enforce_invite_create_limit
from app.domains.simulations import invite_workflow
from app.domains.simulations import service as sim_service
from app.integrations.github import GithubClient, GithubError
from app.services.email import EmailService


async def create_invite_response(
    db: AsyncSession,
    *,
    simulation_id: int,
    payload,
    user_id: int,
    request,
    email_service: EmailService,
    github_client: GithubClient,
):
    enforce_invite_create_limit(request, user_id, payload.inviteEmail)
    try:
        (
            cs,
            sim,
            outcome,
            invite_url,
        ) = await invite_workflow.create_candidate_invite_workflow(
            db,
            simulation_id=simulation_id,
            payload=payload,
            user_id=user_id,
            email_service=email_service,
            github_client=github_client,
        )
    except sim_service.InviteRejectedError as exc:
        return render_invite_error(exc)
    except GithubError as exc:
        raise map_github_error(exc) from exc

    return render_invite_response(cs, invite_url, outcome)
