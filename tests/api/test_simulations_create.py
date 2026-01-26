import pytest
from sqlalchemy import select

from app.core.auth.current_user import get_current_user
from app.domains import Company, Task, User


@pytest.mark.asyncio
async def test_create_simulation_creates_sim_and_5_tasks(
    async_client, async_session, override_dependencies
):
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

    with override_dependencies({get_current_user: lambda: FakeUser()}):
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
        assert data["templateKey"] == "python-fastapi"


@pytest.mark.asyncio
async def test_create_simulation_unauthorized_returns_401(async_client):
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
    async_client, async_session, override_dependencies
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

    with override_dependencies({get_current_user: lambda: FakeCandidate()}):
        payload = {
            "title": "Backend Node Simulation",
            "role": "Backend Engineer",
            "techStack": "Node.js, PostgreSQL",
            "seniority": "Mid",
            "focus": "Build new API feature and debug an issue",
        }

        resp = await async_client.post("/api/simulations", json=payload)
        assert resp.status_code == 403, resp.text


@pytest.mark.asyncio
async def test_create_simulation_with_template_key_persists(
    async_client, async_session, override_dependencies
):
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

    with override_dependencies({get_current_user: lambda: FakeUser()}):
        payload = {
            "title": "Fullstack Simulation",
            "role": "Fullstack Engineer",
            "techStack": "Next.js, FastAPI",
            "seniority": "Senior",
            "focus": "Ship a fullstack feature",
            "templateKey": "monorepo-nextjs-fastapi",
        }

        resp = await async_client.post("/api/simulations", json=payload)
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["templateKey"] == "monorepo-nextjs-fastapi"

        sim_id = data["id"]
        from app.domains.simulations.simulation import Simulation

        saved = await async_session.get(Simulation, sim_id)
        assert saved is not None
        assert saved.template_key == "monorepo-nextjs-fastapi"


@pytest.mark.asyncio
async def test_create_simulation_with_invalid_template_key_returns_422(
    async_client, async_session, override_dependencies
):
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

    with override_dependencies({get_current_user: lambda: FakeUser()}):
        payload = {
            "title": "Backend Node Simulation",
            "role": "Backend Engineer",
            "techStack": "Node.js, PostgreSQL",
            "seniority": "Mid",
            "focus": "Build new API feature and debug an issue",
            "templateKey": "unknown-template-key",
        }

        resp = await async_client.post("/api/simulations", json=payload)
        assert resp.status_code == 422, resp.text
        body = resp.json()
        assert body["errorCode"] == "INVALID_TEMPLATE_KEY"
        detail_list = body["detail"]
        assert isinstance(detail_list, list)
        assert any(
            "Invalid templateKey" in str(item.get("msg")) for item in detail_list
        )
        assert "python-fastapi" in body.get("details", {}).get("allowed", [])


@pytest.mark.asyncio
async def test_seeded_tasks_use_template_catalog(
    async_client, async_session, override_dependencies
):
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

    with override_dependencies({get_current_user: lambda: FakeUser()}):
        payload = {
            "title": "Backend Node Simulation",
            "role": "Backend Engineer",
            "techStack": "Node.js, PostgreSQL",
            "seniority": "Mid",
            "focus": "Build new API feature and debug an issue",
            "templateKey": "node-express-ts",
        }

        resp = await async_client.post("/api/simulations", json=payload)
        assert resp.status_code == 201, resp.text
        sim_id = resp.json()["id"]

        rows = (
            await async_session.execute(
                select(Task)
                .where(Task.simulation_id == sim_id)
                .order_by(Task.day_index)
            )
        ).scalars()
        tasks = list(rows)
        day2 = next(t for t in tasks if t.day_index == 2)
        day3 = next(t for t in tasks if t.day_index == 3)
        assert day2.template_repo == "tenon-hire-dev/tenon-template-node-express-ts"
        assert day3.template_repo == "tenon-hire-dev/tenon-template-node-express-ts"


@pytest.mark.asyncio
async def test_default_template_key_applied(
    async_client, async_session, auth_header_factory
):
    company = Company(name="DefaultCo")
    async_session.add(company)
    await async_session.flush()

    user = User(
        name="Recruiter Default",
        email="recruiter-default@acme.com",
        role="recruiter",
        company_id=company.id,
        password_hash=None,
    )
    async_session.add(user)
    await async_session.commit()

    resp = await async_client.post(
        "/api/simulations",
        headers=auth_header_factory(user),
        json={
            "title": "Backend Node Simulation",
            "role": "Backend Engineer",
            "techStack": "Node.js, PostgreSQL",
            "seniority": "Mid",
            "focus": "Build new API feature and debug an issue",
        },
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["templateKey"] == "python-fastapi"
    sim_id = data["id"]

    rows = (
        await async_session.execute(
            select(Task).where(Task.simulation_id == sim_id).order_by(Task.day_index)
        )
    ).scalars()
    tasks = list(rows)
    day2 = next(t for t in tasks if t.day_index == 2)
    day3 = next(t for t in tasks if t.day_index == 3)
    assert day2.template_repo == "tenon-hire-dev/tenon-template-python-fastapi"
    assert day3.template_repo == "tenon-hire-dev/tenon-template-python-fastapi"


@pytest.mark.asyncio
async def test_list_includes_template_key(
    async_client, async_session, auth_header_factory
):
    company = Company(name="ListCo")
    async_session.add(company)
    await async_session.flush()

    user = User(
        name="Recruiter List",
        email="recruiter-list@acme.com",
        role="recruiter",
        company_id=company.id,
        password_hash=None,
    )
    async_session.add(user)
    await async_session.commit()

    create = await async_client.post(
        "/api/simulations",
        headers=auth_header_factory(user),
        json={
            "title": "ML Simulation",
            "role": "ML Infra Engineer",
            "techStack": "Python",
            "seniority": "Senior",
            "focus": "MLOps",
            "templateKey": "ml-infra-mlops",
        },
    )
    assert create.status_code == 201, create.text

    resp = await async_client.get("/api/simulations", headers=auth_header_factory(user))
    assert resp.status_code == 200, resp.text
    items = resp.json()
    assert len(items) >= 1
    item = next(i for i in items if i["id"] == create.json()["id"])
    assert item["templateKey"] == "ml-infra-mlops"
