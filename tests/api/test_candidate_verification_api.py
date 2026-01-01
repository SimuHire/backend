from datetime import UTC, datetime, timedelta

import pytest

from app.api.dependencies.notifications import get_email_service
from app.domains.candidate_sessions.auth_tokens import hash_token
from app.infra.notifications.email_provider import MemoryEmailProvider
from app.services.email import EmailService
from tests.factories import (
    create_candidate_session,
    create_recruiter,
    create_simulation,
)


async def _seed_candidate_session(async_session):
    recruiter = await create_recruiter(async_session, email="verify-seed@test.com")
    sim, _ = await create_simulation(async_session, created_by=recruiter)
    cs = await create_candidate_session(async_session, simulation=sim)
    return recruiter, sim, cs


@pytest.mark.asyncio
async def test_send_verification_code_and_rate_limit(
    async_client, async_session, override_dependencies
):
    recruiter, sim, cs = await _seed_candidate_session(async_session)
    provider = MemoryEmailProvider()
    email_service = EmailService(provider, sender="SimuHire <noreply@test.com>")

    with override_dependencies({get_email_service: lambda: email_service}):
        res = await async_client.post(
            f"/api/candidate/session/{cs.token}/verification/code/send"
        )
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["status"] == "sent"
        assert body["maskedEmail"].endswith("@example.com")

        await async_session.refresh(cs)
        assert cs.verification_code is not None
        assert cs.verification_code_expires_at is not None
        assert len(provider.sent) == 1

        res2 = await async_client.post(
            f"/api/candidate/session/{cs.token}/verification/code/send"
        )
        assert res2.status_code == 200, res2.text
        body2 = res2.json()
        assert body2["status"] == "rate_limited"
        await async_session.refresh(cs)
        assert cs.verification_email_status == "rate_limited"
        assert len(provider.sent) == 1  # no extra email


@pytest.mark.asyncio
async def test_confirm_verification_code_success(
    async_client, async_session, override_dependencies
):
    recruiter, sim, cs = await _seed_candidate_session(async_session)
    provider = MemoryEmailProvider()
    email_service = EmailService(provider, sender="noreply@test.com")

    with override_dependencies({get_email_service: lambda: email_service}):
        await async_client.post(
            f"/api/candidate/session/{cs.token}/verification/code/send"
        )

    await async_session.refresh(cs)
    code = cs.verification_code
    res = await async_client.post(
        f"/api/candidate/session/{cs.token}/verification/code/confirm",
        json={"code": code},
    )
    assert res.status_code == 200, res.text
    await async_session.refresh(cs)
    assert res.json()["verified"] is True
    assert res.json()["candidateAccessToken"]
    assert res.json()["expiresAt"]
    assert cs.invite_email_verified_at is not None
    assert cs.verification_code is None
    assert cs.verification_code_expires_at is None
    assert cs.candidate_access_token_hash == hash_token(
        res.json()["candidateAccessToken"]
    )
    assert cs.candidate_access_token_expires_at is not None


@pytest.mark.asyncio
async def test_confirm_verification_code_wrong_code(async_client, async_session):
    recruiter = await create_recruiter(async_session, email="wrong@test.com")
    sim, _ = await create_simulation(async_session, created_by=recruiter)
    cs = await create_candidate_session(
        async_session,
        simulation=sim,
        verification_code="123456",
        verification_code_expires_at=datetime.now(UTC) + timedelta(minutes=10),
    )

    res = await async_client.post(
        f"/api/candidate/session/{cs.token}/verification/code/confirm",
        json={"code": "999999"},
    )
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_confirm_verification_code_expired(async_client, async_session):
    recruiter = await create_recruiter(async_session, email="expired@test.com")
    sim, _ = await create_simulation(async_session, created_by=recruiter)
    cs = await create_candidate_session(
        async_session,
        simulation=sim,
        verification_code="123456",
        verification_code_expires_at=datetime.now(UTC) - timedelta(minutes=1),
    )

    res = await async_client.post(
        f"/api/candidate/session/{cs.token}/verification/code/confirm",
        json={"code": "123456"},
    )
    assert res.status_code == 410


@pytest.mark.asyncio
async def test_confirm_verification_code_invalid_format(async_client, async_session):
    recruiter = await create_recruiter(async_session, email="format@test.com")
    sim, _ = await create_simulation(async_session, created_by=recruiter)
    cs = await create_candidate_session(
        async_session,
        simulation=sim,
        verification_code="123456",
        verification_code_expires_at=datetime.now(UTC) + timedelta(minutes=10),
    )

    res = await async_client.post(
        f"/api/candidate/session/{cs.token}/verification/code/confirm",
        json={"code": "12ab"},
    )
    assert res.status_code == 400


@pytest.mark.asyncio
async def test_current_task_with_candidate_access_token(
    async_client, async_session, override_dependencies
):
    recruiter, sim, cs = await _seed_candidate_session(async_session)
    provider = MemoryEmailProvider()
    email_service = EmailService(provider, sender="noreply@test.com")

    with override_dependencies({get_email_service: lambda: email_service}):
        verify_res = await async_client.post(
            f"/api/candidate/session/{cs.token}/verification/code/send"
        )
        assert verify_res.status_code == 200
        await async_session.refresh(cs)
        confirm_res = await async_client.post(
            f"/api/candidate/session/{cs.token}/verification/code/confirm",
            json={"code": cs.verification_code},
        )
    assert confirm_res.status_code == 200
    token = confirm_res.json()["candidateAccessToken"]

    res = await async_client.get(
        f"/api/candidate/session/{cs.id}/current_task",
        headers={
            "Authorization": f"Bearer {token}",
            "x-candidate-session-id": str(cs.id),
        },
    )
    assert res.status_code == 200, res.text

    # Missing auth rejected
    res_unauth = await async_client.get(
        f"/api/candidate/session/{cs.id}/current_task",
        headers={"x-candidate-session-id": str(cs.id)},
    )
    assert res_unauth.status_code == 401

    res_invite_token = await async_client.get(
        f"/api/candidate/session/{cs.id}/current_task",
        headers={
            "Authorization": f"Bearer {cs.token}",
            "x-candidate-session-id": str(cs.id),
        },
    )
    assert res_invite_token.status_code == 401


@pytest.mark.asyncio
async def test_candidate_access_token_expired(async_client, async_session):
    recruiter = await create_recruiter(async_session, email="expired-token@test.com")
    sim, _ = await create_simulation(async_session, created_by=recruiter)
    cs = await create_candidate_session(async_session, simulation=sim)
    token = "expiredtoken"
    cs.candidate_access_token_hash = hash_token(token)
    cs.candidate_access_token_expires_at = datetime.now(UTC) - timedelta(minutes=1)
    await async_session.commit()

    res = await async_client.get(
        f"/api/candidate/session/{cs.id}/current_task",
        headers={
            "Authorization": f"Bearer {token}",
            "x-candidate-session-id": str(cs.id),
        },
    )
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_resend_invite_endpoint(
    async_client, async_session, override_dependencies, auth_header_factory
):
    recruiter = await create_recruiter(async_session, email="resend@test.com")
    sim, _ = await create_simulation(async_session, created_by=recruiter)
    cs = await create_candidate_session(async_session, simulation=sim)

    provider = MemoryEmailProvider()
    email_service = EmailService(provider, sender="noreply@test.com")
    with override_dependencies({get_email_service: lambda: email_service}):
        res = await async_client.post(
            f"/api/simulations/{sim.id}/candidates/{cs.id}/invite/resend",
            headers=auth_header_factory(recruiter),
        )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["inviteEmailStatus"] == "sent"
    assert body["inviteEmailSentAt"] is not None
    assert len(provider.sent) == 1
