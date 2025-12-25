import pytest

from app.core.security.current_user import get_current_user
from app.domain import Company, User
from app.main import app


@pytest.mark.asyncio
async def test_create_simulation_creates_sim_and_5_tasks(async_client, async_session):
    company = Company(name="Acme Inc")
    async_session.add(company)
    await async_session.flush()

    user = User(
        name="Recruiter One",
        email="recruiter1@acme.com",
        role="recruiter",
        company_id=company.id,
        password_hash=None,
    )
    async_session.add(user)
    await async_session.commit()

    class FakeUser:
        id = user.id
        company_id = company.id
        role = "recruiter"

    app.dependency_overrides[get_current_user] = lambda: FakeUser()
    try:
        payload = {
            "title": "Backend Node Simulation",
            "role": "Backend Engineer",
            "techStack": "Node.js, PostgreSQL",
            "seniority": "Mid",
            "focus": "Build new API feature and debug an issue",
        }

        resp = await async_client.post("/api/simulations", json=payload)
        assert resp.status_code == 201, resp.text

        data = resp.json()
        assert "id" in data
        assert len(data["tasks"]) == 5
        assert [t["day_index"] for t in data["tasks"]] == [1, 2, 3, 4, 5]
        assert [t["type"] for t in data["tasks"]] == [
            "design",
            "code",
            "debug",
            "handoff",
            "documentation",
        ]
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_create_simulation_unauthorized_returns_401(async_client):
    app.dependency_overrides.pop(get_current_user, None)

    payload = {
        "title": "Backend Node Simulation",
        "role": "Backend Engineer",
        "techStack": "Node.js, PostgreSQL",
        "seniority": "Mid",
        "focus": "Build new API feature and debug an issue",
    }

    resp = await async_client.post("/api/simulations", json=payload)
    assert resp.status_code == 401, resp.text


@pytest.mark.asyncio
async def test_create_simulation_forbidden_for_non_recruiter(
    async_client, async_session
):
    company = Company(name="Acme Inc")
    async_session.add(company)
    await async_session.flush()

    user = User(
        name="Candidate User",
        email="candidate@acme.com",
        role="candidate",
        company_id=company.id,
        password_hash=None,
    )
    async_session.add(user)
    await async_session.commit()
    await async_session.refresh(user)

    class FakeCandidate:
        id = user.id
        company_id = company.id
        role = "candidate"

    app.dependency_overrides[get_current_user] = lambda: FakeCandidate()
    try:
        payload = {
            "title": "Backend Node Simulation",
            "role": "Backend Engineer",
            "techStack": "Node.js, PostgreSQL",
            "seniority": "Mid",
            "focus": "Build new API feature and debug an issue",
        }

        resp = await async_client.post("/api/simulations", json=payload)
        assert resp.status_code == 403, resp.text
    finally:
        app.dependency_overrides.pop(get_current_user, None)
