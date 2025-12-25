import pytest

from app.domain.submissions import service_candidate as service
from tests.factories import create_recruiter, create_simulation


class DummyTask:
    def __init__(self, simulation_id: int, *, type: str = "code", **attrs):
        self.simulation_id = simulation_id
        self.type = type
        for k, v in attrs.items():
            setattr(self, k, v)


@pytest.mark.asyncio
async def test_build_task_ref_normalizes_zero_based_day_index(async_session):
    recruiter = await create_recruiter(async_session)
    sim, _tasks = await create_simulation(async_session, created_by=recruiter)

    task = DummyTask(simulation_id=sim.id, type="code", day_index=0)
    ref = await service.build_task_ref(async_session, task)
    assert ref.endswith("-day1-code")


@pytest.mark.asyncio
async def test_build_task_ref_uses_focus_when_no_template(async_session):
    recruiter = await create_recruiter(async_session)
    sim, _tasks = await create_simulation(async_session, created_by=recruiter)
    sim.scenario_template = ""
    sim.focus = "Focus Key"
    await async_session.commit()

    task = DummyTask(simulation_id=sim.id, type="debug", day=1)
    ref = await service.build_task_ref(async_session, task)
    assert ref.startswith("focus-key-")
    assert ref.endswith("-debug")
    assert "-day" in ref
