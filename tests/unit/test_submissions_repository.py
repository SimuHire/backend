from __future__ import annotations

import pytest

from app.domains.submissions import repository as submissions_repo
from tests.factories import (
    create_candidate_session,
    create_recruiter,
    create_simulation,
    create_submission,
)


@pytest.mark.asyncio
async def test_find_duplicate_false(async_session):
    recruiter = await create_recruiter(async_session, email="dupfalse@test.com")
    sim, tasks = await create_simulation(async_session, created_by=recruiter)
    cs = await create_candidate_session(async_session, simulation=sim)
    dup = await submissions_repo.find_duplicate(async_session, cs.id, tasks[0].id)
    assert dup is False


@pytest.mark.asyncio
async def test_find_duplicate_true(async_session):
    recruiter = await create_recruiter(async_session, email="duptru@test.com")
    sim, tasks = await create_simulation(async_session, created_by=recruiter)
    cs = await create_candidate_session(async_session, simulation=sim)
    await create_submission(async_session, candidate_session=cs, task=tasks[0])
    dup = await submissions_repo.find_duplicate(async_session, cs.id, tasks[0].id)
    assert dup is True
