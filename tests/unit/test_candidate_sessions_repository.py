import pytest

from app.domains.candidate_sessions import repository as cs_repo
from tests.factories import (
    create_candidate_session,
    create_recruiter,
    create_simulation,
)


@pytest.mark.asyncio
async def test_get_by_token_for_update(async_session):
    recruiter = await create_recruiter(async_session, email="tok@test.com")
    sim, _ = await create_simulation(async_session, created_by=recruiter)
    cs = await create_candidate_session(async_session, simulation=sim)
    found = await cs_repo.get_by_token_for_update(async_session, cs.token)
    assert found is not None
    assert found.id == cs.id
