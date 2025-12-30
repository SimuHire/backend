import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains import Company, Simulation, User


@pytest.mark.asyncio
async def test_create_simulation(async_session: AsyncSession):
    # 1. Create company
    company = Company(name="TestCo")
    async_session.add(company)
    await async_session.flush()

    # 2. Create user (creator of the simulation)
    user = User(
        name="Admin User",
        email="admin@test.com",
        role="admin",
        company_id=company.id,
        password_hash="hashedpw",
    )
    async_session.add(user)
    await async_session.flush()

    # 3. Create simulation referencing both
    sim = Simulation(
        company_id=company.id,
        title="Backend Hiring Simulation",
        role="Backend Engineer",
        tech_stack="Node.js, Postgres",
        seniority="mid",
        scenario_template="backend_v1",
        created_by=user.id,
        status="active",
    )

    async_session.add(sim)
    await async_session.commit()
    await async_session.refresh(sim)

    assert sim.id is not None
    assert sim.created_by == user.id
