from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi import HTTPException

from app.domains.candidate_sessions import service as cs_service
from tests.factories import (
    create_candidate_session,
    create_recruiter,
    create_simulation,
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
async def test_fetch_by_id_and_token_mismatch(async_session):
    recruiter = await create_recruiter(async_session, email="mismatch@sim.com")
    sim, _ = await create_simulation(async_session, created_by=recruiter)
    cs = await create_candidate_session(
        async_session, simulation=sim, status="in_progress"
    )
    with pytest.raises(HTTPException) as excinfo:
        await cs_service.fetch_by_id_and_token(async_session, cs.id, "wrong-token")
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
async def test_fetch_by_id_and_token_success(async_session):
    recruiter = await create_recruiter(async_session, email="ok2@sim.com")
    sim, _ = await create_simulation(async_session, created_by=recruiter)
    cs = await create_candidate_session(
        async_session, simulation=sim, status="in_progress"
    )
    loaded = await cs_service.fetch_by_id_and_token(async_session, cs.id, cs.token)
    assert loaded.id == cs.id
