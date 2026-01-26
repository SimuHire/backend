from __future__ import annotations

from fastapi import HTTPException, status

from app.domains import Task

TEXT_TASK_TYPES = {"design", "documentation", "handoff"}
CODE_TASK_TYPES = {"code", "debug"}


def is_code_task(task: Task) -> bool:
    """Return True if the task requires code (code/debug)."""
    return (task.type or "").lower() in CODE_TASK_TYPES


def validate_submission_payload(task: Task, payload) -> None:
    """Validate submission payload for non-code tasks."""
    task_type = (task.type or "").lower()
    if task_type in TEXT_TASK_TYPES:
        if not payload.contentText or not payload.contentText.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="contentText is required",
            )
        return
    if task_type in CODE_TASK_TYPES:
        return
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Unknown task type",
    )


def validate_run_allowed(task: Task) -> None:
    """Run tests only applies to code/debug tasks."""
    if not is_code_task(task):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Run tests is only available for code tasks",
        )
