from datetime import UTC, datetime

import pytest

from app.domains.notifications import service as notification_service
from app.domains.simulations import service as sim_service
from app.infra.notifications.email_provider import MemoryEmailProvider
from app.services.email import EmailService
from tests.factories import (
    create_candidate_session,
    create_recruiter,
    create_simulation,
)


@pytest.mark.asyncio
async def test_send_invite_email_tracks_status_and_rate_limit(async_session):
    recruiter = await create_recruiter(async_session, email="notify@test.com")
    sim, _ = await create_simulation(async_session, created_by=recruiter)
    cs = await create_candidate_session(async_session, simulation=sim)

    provider = MemoryEmailProvider()
    email_service = EmailService(provider, sender="noreply@test.com")
    now = datetime.now(UTC)

    first = await notification_service.send_invite_email(
        async_session,
        candidate_session=cs,
        simulation=sim,
        invite_url=sim_service.invite_url(cs.token),
        email_service=email_service,
        now=now,
    )
    await async_session.refresh(cs)

    assert first.status == "sent"
    assert cs.invite_email_status == "sent"
    assert cs.invite_email_sent_at is not None
    assert cs.invite_email_error is None
    assert len(provider.sent) == 1
    sent_message = provider.sent[0]
    assert sent_message.to == cs.invite_email
    assert sim.title in sent_message.subject

    # Second send within rate window should be blocked and not call provider.
    second = await notification_service.send_invite_email(
        async_session,
        candidate_session=cs,
        simulation=sim,
        invite_url=sim_service.invite_url(cs.token),
        email_service=email_service,
        now=now,
    )
    await async_session.refresh(cs)

    assert second.status == "rate_limited"
    assert cs.invite_email_status == "rate_limited"
    assert cs.invite_email_error == "Rate limited"
    assert len(provider.sent) == 1  # no extra send
