from dataclasses import dataclass

from app.domain.candidate_sessions.progress import (
    compute_current_task,
    summarize_progress,
)


@dataclass
class FakeTask:
    id: int
    day_index: int


def test_compute_current_task_returns_lowest_missing():
    tasks = [FakeTask(id=2, day_index=2), FakeTask(id=1, day_index=1)]
    # day 1 complete, expect day 2 next even though list order is swapped
    current = compute_current_task(tasks, completed_task_ids={1})
    assert current is not None
    assert current.id == 2
    assert current.day_index == 2


def test_compute_current_task_none_when_all_done():
    tasks = [FakeTask(id=1, day_index=1)]
    assert compute_current_task(tasks, completed_task_ids={1}) is None


def test_summarize_progress_reports_completion():
    completed, total, is_complete = summarize_progress(3, completed_task_ids=[1, 2, 3])
    assert completed == 3
    assert total == 3
    assert is_complete is True
