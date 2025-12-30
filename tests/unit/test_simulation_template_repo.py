from app.domains.simulations.service import _template_repo_for_task
from tests.factories import create_recruiter, create_simulation


async def test_template_repo_mapping_code_and_debug(async_session):
    expected = "simuhire-dev/simuhire-template-python-fastapi"
    assert _template_repo_for_task(2, "code", "python-fastapi") == expected
    assert _template_repo_for_task(3, "debug", "python-fastapi") == expected


async def test_create_simulation_sets_template_repo(async_session):
    recruiter = await create_recruiter(async_session, email="template-map@sim.com")
    _sim, tasks = await create_simulation(async_session, created_by=recruiter)
    for task in tasks:
        if task.type in {"code", "debug"}:
            assert task.template_repo
