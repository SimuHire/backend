import pytest
import pytest_asyncio

from app.main import app
from app.models.candidate_session import CandidateSession
from app.models.company import Company
from app.models.user import User
from app.security.current_user import get_current_user


@pytest_asyncio.fixture
async def recruiter_user(async_session):
    company = Company(name="TestCo")
    async_session.add(company)
    await async_session.flush()  # company.id

    user = User(
        name="Recruiter One",
        email="recruiter@test.com",
        role="recruiter",
        company_id=company.id,
        password_hash=None,
    )
    async_session.add(user)
    await async_session.commit()
    await async_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def authed_client(async_client, recruiter_user):
    async def override_get_current_user():
        return recruiter_user

    app.dependency_overrides[get_current_user] = override_get_current_user
    try:
        yield async_client
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_list_simulations_empty(authed_client):
    resp = await authed_client.get("/api/simulations")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_list_simulations_returns_two(authed_client):
    payload1 = {
        "title": "Sim A",
        "role": "Backend Engineer",
        "techStack": "Node.js, PostgreSQL",
        "seniority": "Mid",
        "focus": "A",
    }
    payload2 = {
        "title": "Sim B",
        "role": "Backend Engineer",
        "techStack": "Node.js, PostgreSQL",
        "seniority": "Mid",
        "focus": "B",
    }

    r1 = await authed_client.post("/api/simulations", json=payload1)
    r2 = await authed_client.post("/api/simulations", json=payload2)
    assert r1.status_code == 201
    assert r2.status_code == 201

    resp = await authed_client.get("/api/simulations")
    assert resp.status_code == 200
    data = resp.json()

    assert len(data) == 2
    titles = {x["title"] for x in data}
    assert titles == {"Sim A", "Sim B"}

    for item in data:
        assert "id" in item
        assert item["role"] == "Backend Engineer"
        assert item["techStack"] == "Node.js, PostgreSQL"
        assert "createdAt" in item
        assert item["numCandidates"] == 0


@pytest.mark.asyncio
async def test_list_simulations_candidate_counts(authed_client, async_session):
    payload = {
        "title": "Sim With Candidates",
        "role": "Backend Engineer",
        "techStack": "Node.js, PostgreSQL",
        "seniority": "Mid",
        "focus": "Counts",
    }

    r = await authed_client.post("/api/simulations", json=payload)
    assert r.status_code == 201
    sim_id = r.json()["id"]

    cs1 = CandidateSession(
        simulation_id=sim_id,
        candidate_user_id=None,
        invite_email="a@example.com",
        token="tok_1",
        status="invited",
        started_at=None,
        completed_at=None,
    )
    cs2 = CandidateSession(
        simulation_id=sim_id,
        candidate_user_id=None,
        invite_email="b@example.com",
        token="tok_2",
        status="invited",
        started_at=None,
        completed_at=None,
    )
    async_session.add_all([cs1, cs2])
    await async_session.commit()

    resp = await authed_client.get("/api/simulations")
    assert resp.status_code == 200
    data = resp.json()

    item = next(x for x in data if x["id"] == sim_id)
    assert item["numCandidates"] == 2


@pytest.mark.asyncio
async def test_list_simulations_does_not_show_other_users(authed_client, async_session):
    other_company = Company(name="OtherCo")
    async_session.add(other_company)
    await async_session.flush()

    other_user = User(
        name="Recruiter Two",
        email="other@test.com",
        role="recruiter",
        company_id=other_company.id,
        password_hash=None,
    )
    async_session.add(other_user)
    await async_session.flush()

    # Create simulation for other user (direct insert)
    from app.models.simulation import Simulation

    other_sim = Simulation(
        title="Other User Sim",
        role="Backend Engineer",
        tech_stack="Node.js, PostgreSQL",
        seniority="Mid",
        focus="Should not appear",
        scenario_template="default-5day-node-postgres",
        company_id=other_company.id,
        created_by=other_user.id,
    )
    async_session.add(other_sim)
    await async_session.commit()

    resp = await authed_client.get("/api/simulations")
    assert resp.status_code == 200
    titles = {x["title"] for x in resp.json()}
    assert "Other User Sim" not in titles
