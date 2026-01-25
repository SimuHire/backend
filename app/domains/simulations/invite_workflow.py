from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.github_native import GithubClient
from app.domains.notifications import service as notification_service
from app.domains.simulations import invite_preprovision
from app.domains.simulations import service as sim_service


async def create_candidate_invite_workflow(
    db: AsyncSession,
    *,
    simulation_id: int,
    payload,
    user_id: int,
    email_service,
    github_client: GithubClient,
    now: datetime | None = None,
):
    sim, tasks = await sim_service.require_owned_simulation_with_tasks(
        db, simulation_id, user_id
    )
    now = now or datetime.now(UTC)
    cs, outcome = await sim_service.create_or_resend_invite(
        db, simulation_id, payload, now=now
    )
    await invite_preprovision.preprovision_workspaces(
        db, cs, tasks, github_client, now=now
    )
    invite_url = sim_service.invite_url(cs.token)
    await notification_service.send_invite_email(
        db,
        candidate_session=cs,
        simulation=sim,
        invite_url=invite_url,
        email_service=email_service,
        now=now,
    )
    return cs, sim, outcome, invite_url
