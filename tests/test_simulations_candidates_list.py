from datetime import UTC, datetime

import pytest

from app.models.candidate_session import CandidateSession
from app.models.company import Company
from app.models.execution_profile import ExecutionProfile
from app.models.simulation import Simulation
from app.models.user import User


@pytest.mark.asyncio
async def seed_recruiter(async_session, *, email: str, company_name: str, name: str):
    company = Company(name=company_name)
    async_session.add(company)
    await async_session.flush()

    user = User(
        name=name,
        email=email,
        role="recruiter",
        company_id=company.id,
        password_hash=None,
    )
    async_session.add(user)
    await async_session.commit()
    return user, company


@pytest.mark.asyncio
async def test_simulation_with_no_candidate_sessions_returns_empty_list(
    async_client, async_session
):
    user, company = await seed_recruiter(
        async_session, email="r1@acme.com", company_name="Acme", name="Recruiter One"
    )

    sim = Simulation(
        title="Test Sim",
        role="Backend Engineer",
        tech_stack="Node.js + Postgres",
        seniority="Mid",
        focus="",
        scenario_template="default-5day-node-postgres",
        company_id=company.id,
        created_by=user.id,
    )
    async_session.add(sim)
    await async_session.commit()

    resp = await async_client.get(
        f"/api/simulations/{sim.id}/candidates",
        headers={"x-dev-user-email": user.email},
    )
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_simulation_with_multiple_sessions_returns_all_and_has_report(
    async_client, async_session
):
    user, company = await seed_recruiter(
        async_session, email="r2@acme.com", company_name="Acme2", name="Recruiter Two"
    )

    sim = Simulation(
        title="Sim With Candidates",
        role="Backend Engineer",
        tech_stack="Node.js + Postgres",
        seniority="Mid",
        focus="",
        scenario_template="default-5day-node-postgres",
        company_id=company.id,
        created_by=user.id,
    )
    async_session.add(sim)
    await async_session.flush()

    cs1 = CandidateSession(
        simulation_id=sim.id,
        candidate_name="Ada Lovelace",
        invite_email="ada@example.com",
        token="tok-1",
        status="not_started",
        expires_at=None,
    )
    cs2 = CandidateSession(
        simulation_id=sim.id,
        candidate_name="Bob",
        invite_email="bob@example.com",
        token="tok-2",
        status="completed",
        started_at=datetime.now(UTC),
        completed_at=datetime.now(UTC),
        expires_at=None,
    )
    async_session.add_all([cs1, cs2])
    await async_session.flush()

    async_session.add(
        ExecutionProfile(candidate_session_id=cs2.id, generated_at=datetime.now(UTC))
    )
    await async_session.commit()

    resp = await async_client.get(
        f"/api/simulations/{sim.id}/candidates",
        headers={"x-dev-user-email": user.email},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2

    by_id = {row["candidateSessionId"]: row for row in data}

    assert by_id[cs1.id]["inviteEmail"] == "ada@example.com"
    assert by_id[cs1.id]["candidateName"] == "Ada Lovelace"
    assert by_id[cs1.id]["status"] == "not_started"
    assert by_id[cs1.id]["hasReport"] is False

    assert by_id[cs2.id]["inviteEmail"] == "bob@example.com"
    assert by_id[cs2.id]["candidateName"] == "Bob"
    assert by_id[cs2.id]["status"] == "completed"
    assert by_id[cs2.id]["hasReport"] is True


@pytest.mark.asyncio
async def test_recruiter_who_does_not_own_simulation_gets_404(
    async_client, async_session
):
    owner, owner_company = await seed_recruiter(
        async_session, email="owner@acme.com", company_name="AcmeOwner", name="Owner"
    )
    other, _ = await seed_recruiter(
        async_session,
        email="other@beta.com",
        company_name="Beta",
        name="Other Recruiter",
    )

    sim = Simulation(
        title="Private Sim",
        role="Backend Engineer",
        tech_stack="Node.js + Postgres",
        seniority="Mid",
        focus="",
        scenario_template="default-5day-node-postgres",
        company_id=owner_company.id,
        created_by=owner.id,
    )
    async_session.add(sim)
    await async_session.commit()

    resp = await async_client.get(
        f"/api/simulations/{sim.id}/candidates",
        headers={"x-dev-user-email": other.email},
    )
    assert resp.status_code == 404
