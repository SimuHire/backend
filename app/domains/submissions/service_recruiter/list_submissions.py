from __future__ import annotations
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import load_only
from app.domains import CandidateSession, Simulation, Submission, Task

async def list_submissions(
    db: AsyncSession,
    recruiter_id: int,
    candidate_session_id: int | None,
    task_id: int | None,
    limit: int | None = None,
    offset: int = 0,
) -> list[tuple[Submission, Task]]:
    stmt = (
        select(Submission, Task)
        .join(Task, Task.id == Submission.task_id)
        .join(CandidateSession, CandidateSession.id == Submission.candidate_session_id)
        .join(Simulation, Simulation.id == CandidateSession.simulation_id)
        .where(Simulation.created_by == recruiter_id)
        .order_by(Submission.submitted_at.desc())
        .options(
            load_only(
                Submission.id,
                Submission.candidate_session_id,
                Submission.task_id,
                Submission.submitted_at,
                Submission.code_repo_path,
                Submission.workflow_run_id,
                Submission.commit_sha,
                Submission.diff_summary_json,
                Submission.tests_passed,
                Submission.tests_failed,
                Submission.test_output,
                Submission.last_run_at,
            ),
            load_only(Task.id, Task.day_index, Task.type),
        )
    )

    if candidate_session_id is not None:
        stmt = stmt.where(Submission.candidate_session_id == candidate_session_id)
    if task_id is not None:
        stmt = stmt.where(Submission.task_id == task_id)
    if offset:
        stmt = stmt.offset(offset)
    if limit is not None:
        stmt = stmt.limit(limit)

    return (await db.execute(stmt)).all()
