from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import CandidateSession, Simulation, Submission, Task


def derive_test_status(
    passed: int | None, failed: int | None, output: str | None
) -> str | None:
    """Summarize test results into a status string."""
    if passed is None and failed is None and (output is None or output.strip() == ""):
        return None
    if failed is not None and failed > 0:
        return "failed"
    if passed is not None and (failed is None or failed == 0):
        return "passed"
    return "unknown"


async def fetch_detail(
    db: AsyncSession, submission_id: int, recruiter_id: int
) -> tuple[Submission, Task, CandidateSession, Simulation]:
    """Load submission with task/session/simulation; enforce ownership."""
    stmt = (
        select(Submission, Task, CandidateSession, Simulation)
        .join(Task, Task.id == Submission.task_id)
        .join(CandidateSession, CandidateSession.id == Submission.candidate_session_id)
        .join(Simulation, Simulation.id == CandidateSession.simulation_id)
        .where(Submission.id == submission_id)
        .where(Simulation.created_by == recruiter_id)
    )
    row = (await db.execute(stmt)).first()
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Submission not found"
        )
    return row


async def list_submissions(
    db: AsyncSession,
    recruiter_id: int,
    candidate_session_id: int | None,
    task_id: int | None,
) -> list[tuple[Submission, Task, CandidateSession, Simulation]]:
    """List submissions for simulations owned by recruiter with optional filters."""
    stmt = (
        select(Submission, Task, CandidateSession, Simulation)
        .join(Task, Task.id == Submission.task_id)
        .join(CandidateSession, CandidateSession.id == Submission.candidate_session_id)
        .join(Simulation, Simulation.id == CandidateSession.simulation_id)
        .where(Simulation.created_by == recruiter_id)
        .order_by(Submission.submitted_at.desc())
    )

    if candidate_session_id is not None:
        stmt = stmt.where(Submission.candidate_session_id == candidate_session_id)
    if task_id is not None:
        stmt = stmt.where(Submission.task_id == task_id)

    rows = (await db.execute(stmt)).all()
    return rows
