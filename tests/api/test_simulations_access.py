import pytest

from tests.factories import create_recruiter


@pytest.mark.asyncio
async def test_create_simulation_forbidden_for_non_recruiter(
    async_client, async_session
):
    candidate_user = await create_recruiter(
        async_session, email="candidate@sim.com", name="Cand", company_name="Cand Co"
    )
    # flip role to candidate to exercise 403 path
    candidate_user.role = "candidate"
    await async_session.commit()

    res = await async_client.post(
        "/api/simulations",
        headers={"x-dev-user-email": candidate_user.email},
        json={
            "title": "Should Fail",
            "role": "Backend",
            "techStack": "Python",
            "seniority": "Mid",
            "focus": "N/A",
        },
    )
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_list_simulations_forbidden_for_non_recruiter(
    async_client, async_session
):
    candidate_user = await create_recruiter(
        async_session, email="candidate2@sim.com", name="Cand2", company_name="Cand2 Co"
    )
    candidate_user.role = "candidate"
    await async_session.commit()

    res = await async_client.get(
        "/api/simulations", headers={"x-dev-user-email": candidate_user.email}
    )
    assert res.status_code == 403
