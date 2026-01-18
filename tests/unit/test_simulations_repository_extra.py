import pytest

from app.domains.simulations import repository as sim_repo


@pytest.mark.asyncio
async def test_simulations_repository_empty_paths(async_session):
    # list_with_candidate_counts with no data should still return iterable
    rows = await sim_repo.list_with_candidate_counts(async_session, user_id=0)
    assert list(rows) == []

    sim, tasks = await sim_repo.get_owned_with_tasks(async_session, 1, 1)
    assert sim is None and tasks == []


@pytest.mark.asyncio
async def test_simulations_repository_with_tasks(async_session):
    # Create a simple simulation with one task to ensure tasks are returned.
    from tests.factories import create_recruiter, create_simulation

    recruiter = await create_recruiter(async_session, email="repo@test.com")
    sim, tasks = await create_simulation(async_session, created_by=recruiter)

    found_sim, found_tasks = await sim_repo.get_owned_with_tasks(
        async_session, sim.id, recruiter.id
    )
    assert found_sim.id == sim.id
    assert [t.id for t in found_tasks] == [t.id for t in tasks]
