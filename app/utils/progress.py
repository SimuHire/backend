from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol, TypeVar


class TaskLike(Protocol):
    """Minimal interface needed for progress calculations."""

    id: int
    day_index: int


TaskType = TypeVar("TaskType", bound=TaskLike)


def compute_current_task(
    tasks: Iterable[TaskType], completed_task_ids: Iterable[int]
) -> TaskType | None:
    """Return the next task (lowest day_index) not yet completed.

    Tasks are sorted by day_index to be order-agnostic for callers.
    """
    completed = {int(tid) for tid in completed_task_ids}
    ordered_tasks = sorted(tasks, key=lambda t: t.day_index)
    return next((task for task in ordered_tasks if task.id not in completed), None)


def summarize_progress(
    total_tasks: int, completed_task_ids: Iterable[int]
) -> tuple[int, int, bool]:
    """Return (completed_count, total_count, is_complete)."""
    completed_set = {int(tid) for tid in completed_task_ids}
    completed = len(completed_set)
    total = max(int(total_tasks), 0)
    is_complete = total > 0 and completed >= total
    return completed, total, is_complete
