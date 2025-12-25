from dataclasses import dataclass

import hypothesis.strategies as st
from hypothesis import given

from app.utils.progress import compute_current_task, summarize_progress


@dataclass
class FakeTask:
    id: int
    day_index: int


@given(
    total_tasks=st.integers(min_value=1, max_value=10),
    completed_ids=st.lists(st.integers(min_value=1, max_value=15), unique=True),
)
def test_current_task_monotonic(total_tasks: int, completed_ids: list[int]):
    """Property: next task is always the smallest missing day_index."""
    tasks = [FakeTask(id=i, day_index=i) for i in range(1, total_tasks + 1)]
    completed = {cid for cid in completed_ids if cid <= total_tasks}

    current = compute_current_task(tasks, completed)
    completed_count, total_count, is_complete = summarize_progress(
        total_tasks, completed
    )

    assert total_count == total_tasks
    if is_complete:
        assert current is None
    else:
        expected = min(set(range(1, total_tasks + 1)) - completed)
        assert current is not None
        assert current.day_index == expected
