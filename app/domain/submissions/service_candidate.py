from __future__ import annotations

from datetime import datetime

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import CandidateSession, Submission, Task
from app.domain.candidate_sessions import service as cs_service
from app.domain.simulations import tasks_repository as tasks_repo
from app.domain.submissions import repository as submissions_repo

TEXT_TASK_TYPES = {"design", "documentation", "handoff"}
CODE_TASK_TYPES = {"code", "debug"}


async def load_task_or_404(db: AsyncSession, task_id: int) -> Task:
    """Fetch a task by id or raise 404."""
    task = await tasks_repo.get_by_id(db, task_id)
    if task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Task not found"
        )
    return task


def ensure_task_belongs(task: Task, candidate_session: CandidateSession) -> None:
    """Ensure the task is part of the candidate's simulation."""
    if task.simulation_id != candidate_session.simulation_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Task not found"
        )


async def ensure_not_duplicate(
    db: AsyncSession, candidate_session_id: int, task_id: int
) -> None:
    """Guard against duplicate submissions for a task."""
    if await submissions_repo.find_duplicate(db, candidate_session_id, task_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Task already submitted"
        )


def ensure_in_order(current_task: Task | None, target_task_id: int) -> None:
    """Verify the submission is for the current task in sequence."""
    if current_task is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Simulation already completed"
        )
    if current_task.id != target_task_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Task out of order"
        )


def validate_payload(task: Task, payload) -> None:
    """Validate submission payload based on task type."""
    task_type = (task.type or "").lower()

    if task_type in TEXT_TASK_TYPES:
        if not payload.contentText or not payload.contentText.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="contentText is required",
            )
    elif task_type in CODE_TASK_TYPES:
        has_code_blob = bool(payload.codeBlob and payload.codeBlob.strip())
        has_files = bool(payload.files)
        if not (has_code_blob or has_files):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="codeBlob or files is required",
            )
    else:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unknown task type",
        )


def validate_run_payload(task: Task, payload) -> None:
    """Validate sandbox run payload for code/debug tasks."""
    task_type = (task.type or "").lower()
    if task_type not in CODE_TASK_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Run tests is only available for code tasks",
        )
    has_code_blob = bool(payload.codeBlob and payload.codeBlob.strip())
    has_files = bool(payload.files)
    if not (has_code_blob or has_files):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="codeBlob or files is required",
        )


async def build_task_ref(db: AsyncSession, task: Task) -> str:
    """Derive a stable task reference for sandbox bundles."""
    scenario = await submissions_repo.simulation_template(db, task.simulation_id)
    scenario_prefix = (scenario or "default").strip().replace(" ", "-").lower()
    task_type = (task.type or "task").strip().lower()

    day_value = None
    for attr in ("day_index", "day", "day_number"):
        if hasattr(task, attr):
            val = getattr(task, attr, None)
            if val is not None:
                day_value = int(val)
                break
    if day_value is None:
        for attr in ("order", "position", "sequence"):
            if hasattr(task, attr):
                val = getattr(task, attr, None)
                if val is not None:
                    day_value = int(val)
                    break

    derived_default = False
    if day_value is None:
        day_value = 1
        derived_default = True

    if not derived_default and 0 <= day_value <= 4:
        day_value += 1
    if day_value <= 0:
        day_value = 1
    day_part = f"day{day_value}"

    return f"{scenario_prefix}-{day_part}-{task_type}"


async def create_submission(
    db: AsyncSession,
    candidate_session: CandidateSession,
    task: Task,
    payload,
    *,
    now: datetime,
) -> Submission:
    """Persist a submission with conflict handling."""
    sub = Submission(
        candidate_session_id=candidate_session.id,
        task_id=task.id,
        submitted_at=now,
        content_text=payload.contentText,
        code_blob=payload.codeBlob,
        code_repo_path=None,
    )
    db.add(sub)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Task already submitted"
        ) from exc
    await db.refresh(sub)
    return sub


async def progress_after_submission(
    db: AsyncSession, candidate_session: CandidateSession, *, now: datetime
) -> tuple[int, int, bool]:
    """Recompute progress and update completion status if applicable."""
    (
        _,
        completed_task_ids,
        _current,
        completed,
        total,
        is_complete,
    ) = await cs_service.progress_snapshot(db, candidate_session)

    if is_complete and candidate_session.status != "completed":
        candidate_session.status = "completed"
        if candidate_session.completed_at is None:
            candidate_session.completed_at = now
        await db.commit()
        await db.refresh(candidate_session)

    return completed, total, is_complete
