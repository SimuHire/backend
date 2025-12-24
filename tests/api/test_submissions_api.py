import pytest

from tests.factories import (
    create_candidate_session,
    create_recruiter,
    create_simulation,
    create_submission,
)


@pytest.mark.asyncio
async def test_submissions_list_forbidden_for_non_recruiter(
    async_client, async_session
):
    user = await create_recruiter(
        async_session, email="nonrecruiter@sim.com", name="NR", company_name="NR Co"
    )
    user.role = "candidate"
    await async_session.commit()

    res = await async_client.get(
        "/api/submissions", headers={"x-dev-user-email": user.email}
    )
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_submissions_detail_404_when_not_owner(async_client, async_session):
    owner = await create_recruiter(async_session, email="owner@sim.com")
    other = await create_recruiter(async_session, email="other@sim.com")
    sim, tasks = await create_simulation(async_session, created_by=owner)
    cs = await create_candidate_session(
        async_session, simulation=sim, status="in_progress"
    )
    sub = await create_submission(
        async_session,
        candidate_session=cs,
        task=tasks[0],
        content_text="answer",
    )

    res = await async_client.get(
        f"/api/submissions/{sub.id}",
        headers={"x-dev-user-email": other.email},
    )
    assert res.status_code == 404
