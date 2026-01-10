from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.domains.candidate_sessions import service as cs_service
from app.infra.config import settings
from app.infra.security.principal import Principal
from tests.factories import (
    create_candidate_session,
    create_recruiter,
    create_simulation,
)


def _principal(email: str) -> Principal:
    email_claim = settings.auth.AUTH0_EMAIL_CLAIM
    permissions_claim = settings.auth.AUTH0_PERMISSIONS_CLAIM
    return Principal(
        sub=f"auth0|{email}",
        email=email,
        name=email.split("@")[0],
        roles=[],
        permissions=["candidate:access"],
        claims={
            "sub": f"auth0|{email}",
            "email": email,
            email_claim: email,
            "permissions": ["candidate:access"],
            permissions_claim: ["candidate:access"],
        },
    )


@pytest.mark.asyncio
async def test_fetch_by_token_404(async_session):
    with pytest.raises(HTTPException) as excinfo:
        await cs_service.fetch_by_token(async_session, "missing-token")
    assert excinfo.value.status_code == 404


@pytest.mark.asyncio
async def test_fetch_by_token_expired(async_session):
    recruiter = await create_recruiter(async_session, email="expire@sim.com")
    sim, _ = await create_simulation(async_session, created_by=recruiter)
    cs = await create_candidate_session(
        async_session,
        simulation=sim,
        status="in_progress",
        expires_in_days=-1,
    )
    now = datetime.now(UTC)
    with pytest.raises(HTTPException) as excinfo:
        await cs_service.fetch_by_token(async_session, cs.token, now=now)
    assert excinfo.value.status_code == 410


@pytest.mark.asyncio
async def test_fetch_owned_session_mismatch(async_session):
    recruiter = await create_recruiter(async_session, email="mismatch@sim.com")
    sim, _ = await create_simulation(async_session, created_by=recruiter)
    cs = await create_candidate_session(async_session, simulation=sim)
    principal = _principal("other@example.com")
    with pytest.raises(HTTPException) as excinfo:
        await cs_service.fetch_owned_session(async_session, cs.id, principal)
    assert excinfo.value.status_code == 403


@pytest.mark.asyncio
async def test_load_tasks_empty(async_session):
    recruiter = await create_recruiter(async_session, email="empty@sim.com")
    sim, tasks = await create_simulation(async_session, created_by=recruiter)
    for t in tasks:
        await async_session.delete(t)
    await async_session.commit()
    with pytest.raises(HTTPException) as excinfo:
        await cs_service.load_tasks(async_session, sim.id)
    assert excinfo.value.status_code == 500


@pytest.mark.asyncio
async def test_fetch_by_token_success(async_session):
    recruiter = await create_recruiter(async_session, email="ok@sim.com")
    sim, _ = await create_simulation(async_session, created_by=recruiter)
    cs = await create_candidate_session(
        async_session, simulation=sim, status="in_progress"
    )
    loaded = await cs_service.fetch_by_token(async_session, cs.token)
    assert loaded.id == cs.id


@pytest.mark.asyncio
async def test_fetch_owned_session_success(async_session):
    recruiter = await create_recruiter(async_session, email="ok2@sim.com")
    sim, _ = await create_simulation(async_session, created_by=recruiter)
    cs = await create_candidate_session(async_session, simulation=sim)
    principal = _principal(cs.invite_email)
    loaded = await cs_service.fetch_owned_session(async_session, cs.id, principal)
    assert loaded.id == cs.id


@pytest.mark.asyncio
async def test_fetch_owned_session_expired(async_session):
    recruiter = await create_recruiter(async_session, email="expired-token@sim.com")
    sim, _ = await create_simulation(async_session, created_by=recruiter)
    cs = await create_candidate_session(
        async_session,
        simulation=sim,
        status="in_progress",
        expires_in_days=-1,
    )
    principal = _principal(cs.invite_email)
    with pytest.raises(HTTPException) as excinfo:
        await cs_service.fetch_owned_session(async_session, cs.id, principal)
    assert excinfo.value.status_code == 410


@pytest.mark.asyncio
async def test_claim_invite_with_principal(async_session):
    recruiter = await create_recruiter(async_session, email="verify@sim.com")
    sim, _ = await create_simulation(async_session, created_by=recruiter)
    cs = await create_candidate_session(
        async_session, simulation=sim, status="not_started"
    )
    principal = _principal(cs.invite_email)

    verified = await cs_service.claim_invite_with_principal(
        async_session, cs.token, principal
    )
    assert verified.status == "in_progress"
    assert verified.started_at is not None
    assert verified.candidate_auth0_sub == principal.sub
    assert verified.candidate_email == cs.invite_email


@pytest.mark.asyncio
async def test_claim_invite_email_mismatch(async_session):
    recruiter = await create_recruiter(async_session, email="verify-mismatch@sim.com")
    sim, _ = await create_simulation(async_session, created_by=recruiter)
    cs = await create_candidate_session(async_session, simulation=sim)

    principal = _principal("wrong@example.com")
    with pytest.raises(HTTPException) as excinfo:
        await cs_service.claim_invite_with_principal(async_session, cs.token, principal)
    assert excinfo.value.status_code == 403


def test_normalize_email_non_string():
    assert cs_service._normalize_email(123) == ""


def test_ensure_email_match_missing_email():
    cs = SimpleNamespace(invite_email="jane@example.com", candidate_email=None)
    with pytest.raises(HTTPException) as excinfo:
        cs_service._ensure_email_match(cs, "")
    assert excinfo.value.status_code == 400
