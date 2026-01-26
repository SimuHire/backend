from __future__ import annotations

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.domains import CandidateSession, Simulation
from app.domains.notifications.invite_dispatch import (
    dispatch_invite_email,
    record_send_result,
)
from app.domains.notifications.invite_rate_limit import (
    record_rate_limit,
    should_rate_limit,
)
from app.domains.notifications.invite_time import utc_now
from app.services.email import EmailSendResult, EmailService


async def send_invite_email(
    db: AsyncSession,
    *,
    candidate_session: CandidateSession,
    simulation: Simulation,
    invite_url: str,
    email_service: EmailService,
    now: datetime | None = None,
) -> EmailSendResult:
    resolved_now = utc_now(now)
    if should_rate_limit(candidate_session, resolved_now):
        return await record_rate_limit(db, candidate_session, resolved_now)

    result = await dispatch_invite_email(
        email_service,
        candidate_session=candidate_session,
        simulation=simulation,
        invite_url=invite_url,
    )
    return await record_send_result(db, candidate_session, resolved_now, result)
