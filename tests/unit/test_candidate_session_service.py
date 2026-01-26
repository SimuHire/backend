from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi import HTTPException

from app.core.auth.principal import Principal
from app.core.settings import settings
from app.domains.candidate_sessions import service as cs_service
from tests.factories import (
    create_candidate_session,
    create_recruiter,
    create_simulation,
    create_submission,
)


def _principal(email: str, *, email_verified: bool | None = None) -> Principal:
    email_claim = settings.auth.AUTH0_EMAIL_CLAIM
    permissions_claim = settings.auth.AUTH0_PERMISSIONS_CLAIM
    claims = {
        "sub": f"auth0|{email}",
        "email": email,
        email_claim: email,
        "permissions": ["candidate:access"],
        permissions_claim: ["candidate:access"],
    }
    if email_verified is not None:
        claims["email_verified"] = email_verified
    return Principal(
        sub=f"auth0|{email}",
        email=email,
        name=email.split("@")[0],
        roles=[],
        permissions=["candidate:access"],
        claims=claims,
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
    assert excinfo.value.status_code == 404


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
async def test_fetch_by_token_for_update_not_found(async_session):
    with pytest.raises(HTTPException) as excinfo:
        await cs_service.fetch_by_token_for_update(async_session, "missing")
    assert excinfo.value.status_code == 404


@pytest.mark.asyncio
async def test_fetch_owned_session_not_found(async_session):
    principal = _principal("nobody@example.com")
    with pytest.raises(HTTPException) as excinfo:
        await cs_service.fetch_owned_session(async_session, 9999, principal)
    assert excinfo.value.status_code == 404


@pytest.mark.asyncio
async def test_fetch_owned_session_stored_sub_mismatch(async_session):
    recruiter = await create_recruiter(async_session, email="stored-sub@sim.com")
    sim, _ = await create_simulation(async_session, created_by=recruiter)
    cs = await create_candidate_session(async_session, simulation=sim)
    cs.candidate_auth0_sub = "auth0|other"
    await async_session.commit()

    principal = _principal(cs.invite_email)
    with pytest.raises(HTTPException) as excinfo:
        await cs_service.fetch_owned_session(async_session, cs.id, principal)
    assert excinfo.value.status_code == 404


@pytest.mark.asyncio
async def test_fetch_owned_session_updates_status(async_session):
    recruiter = await create_recruiter(async_session, email="promote@sim.com")
    sim, _ = await create_simulation(async_session, created_by=recruiter)
    cs = await create_candidate_session(
        async_session, simulation=sim, status="not_started"
    )
    principal = _principal(cs.invite_email)
    cs.candidate_auth0_sub = principal.sub
    cs.candidate_email = None
    await async_session.commit()

    refreshed = await cs_service.fetch_owned_session(async_session, cs.id, principal)
    assert refreshed.status == "in_progress"
    assert refreshed.candidate_auth0_email == principal.email


class _DummyDB:
    def __init__(self, cs_for_update):
        self.cs_for_update = cs_for_update

    def begin_nested(self):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def commit(self):
        self.committed = True

    async def refresh(self, obj):
        self.refreshed = obj


@pytest.mark.asyncio
async def test_fetch_owned_session_missing_after_lock(monkeypatch):
    principal = _principal("lock@test.com")
    cs_stub = type(
        "CS",
        (),
        {
            "id": 1,
            "simulation_id": 1,
            "candidate_auth0_sub": None,
            "candidate_email": "lock@test.com",
            "invite_email": "lock@test.com",
            "expires_at": None,
            "status": "not_started",
        },
    )()

    async def fake_get_by_id(db, session_id):
        return cs_stub

    async def fake_get_by_id_for_update(db, session_id):
        return None

    monkeypatch.setattr(cs_service.cs_repo, "get_by_id", fake_get_by_id)
    monkeypatch.setattr(
        cs_service.cs_repo, "get_by_id_for_update", fake_get_by_id_for_update
    )
    dummy_db = _DummyDB(None)
    with pytest.raises(HTTPException) as excinfo:
        await cs_service.fetch_owned_session(
            dummy_db, 1, principal, now=datetime.now(UTC)
        )
    assert excinfo.value.status_code == 404


@pytest.mark.asyncio
async def test_fetch_owned_session_conflict_after_lock(monkeypatch):
    principal = _principal("conflict@test.com")
    cs_stub = type(
        "CS",
        (),
        {
            "id": 1,
            "simulation_id": 1,
            "candidate_auth0_sub": None,
            "candidate_email": "conflict@test.com",
            "invite_email": "conflict@test.com",
            "expires_at": None,
            "status": "not_started",
        },
    )()
    conflicting = type(
        "CS",
        (),
        {
            "id": 1,
            "simulation_id": 1,
            "candidate_auth0_sub": "other",
            "candidate_email": "conflict@test.com",
            "invite_email": "conflict@test.com",
            "expires_at": None,
            "status": "not_started",
        },
    )()

    async def fake_get_by_id(db, session_id):
        return cs_stub

    async def fake_get_by_id_for_update(db, session_id):
        return conflicting

    monkeypatch.setattr(cs_service.cs_repo, "get_by_id", fake_get_by_id)
    monkeypatch.setattr(
        cs_service.cs_repo, "get_by_id_for_update", fake_get_by_id_for_update
    )
    dummy_db = _DummyDB(conflicting)
    with pytest.raises(HTTPException) as excinfo:
        await cs_service.fetch_owned_session(
            dummy_db, 1, principal, now=datetime.now(UTC)
        )
    assert excinfo.value.status_code == 404


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
    assert excinfo.value.status_code == 404


@pytest.mark.asyncio
async def test_claim_invite_requires_verified_email(async_session):
    recruiter = await create_recruiter(async_session, email="verify-req@sim.com")
    sim, _ = await create_simulation(async_session, created_by=recruiter)
    cs = await create_candidate_session(async_session, simulation=sim)
    principal = _principal(cs.invite_email, email_verified=False)

    with pytest.raises(HTTPException) as excinfo:
        await cs_service.claim_invite_with_principal(async_session, cs.token, principal)
    assert excinfo.value.status_code == 403


@pytest.mark.asyncio
async def test_claim_invite_missing_email_claim(async_session):
    recruiter = await create_recruiter(async_session, email="missing-email@sim.com")
    sim, _ = await create_simulation(async_session, created_by=recruiter)
    cs = await create_candidate_session(async_session, simulation=sim)
    principal = _principal("", email_verified=True)

    with pytest.raises(HTTPException) as excinfo:
        await cs_service.claim_invite_with_principal(async_session, cs.token, principal)
    assert excinfo.value.status_code == 403


def test_normalize_email_non_string():
    assert cs_service._normalize_email(123) == ""


def test_ensure_candidate_ownership_variants():
    principal = _principal("owner@example.com")
    cs = type(
        "CS",
        (),
        {
            "invite_email": "owner@example.com",
            "candidate_auth0_sub": "auth0|owner@example.com",
            "candidate_email": None,
            "candidate_auth0_email": None,
            "status": "in_progress",
        },
    )()
    changed = cs_service._ensure_candidate_ownership(
        cs, principal, now=datetime.now(UTC)
    )
    assert changed is True
    assert cs.candidate_email == "owner@example.com"

    cs_different = type(
        "CS",
        (),
        {
            "invite_email": "owner@example.com",
            "candidate_auth0_sub": "other",
            "status": "in_progress",
        },
    )()
    with pytest.raises(HTTPException):
        cs_service._ensure_candidate_ownership(
            cs_different, principal, now=datetime.now(UTC)
        )


@pytest.mark.asyncio
async def test_invite_list_for_principal_includes_progress(async_session):
    recruiter = await create_recruiter(async_session, email="list@sim.com")
    sim, tasks = await create_simulation(async_session, created_by=recruiter)
    cs = await create_candidate_session(
        async_session,
        simulation=sim,
        invite_email="jane@example.com",
        status="in_progress",
    )
    await create_submission(
        async_session,
        candidate_session=cs,
        task=tasks[0],
        content_text="day1",
    )
    await async_session.commit()

    principal = _principal(cs.invite_email)
    invites = await cs_service.invite_list_for_principal(async_session, principal)
    assert len(invites) == 1
    invite = invites[0]
    assert invite.candidateSessionId == cs.id
    assert invite.progress.completed == 1
    assert invite.progress.total == len(tasks)
