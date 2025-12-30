from __future__ import annotations

import pytest

from app.domains.tasks import repository as tasks_repository
from tests.factories import create_recruiter, create_simulation


@pytest.mark.asyncio
async def test_get_by_id_returns_none_when_missing(async_session):
    result = await tasks_repository.get_by_id(async_session, 9999)
    assert result is None


@pytest.mark.asyncio
async def test_get_by_id_returns_task(async_session):
    recruiter = await create_recruiter(async_session, email="taskrepo@test.com")
    sim, tasks = await create_simulation(async_session, created_by=recruiter)
    task = tasks[0]
    found = await tasks_repository.get_by_id(async_session, task.id)
    assert found.id == task.id
