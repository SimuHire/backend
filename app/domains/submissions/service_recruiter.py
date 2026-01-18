from __future__ import annotations

import json
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import load_only

from app.domains import CandidateSession, Simulation, Submission, Task


def derive_test_status(
    passed: int | None, failed: int | None, output: dict[str, Any] | str | None
) -> str | None:
    """Summarize test results into a status string."""
    parsed: dict[str, Any] | None = output if isinstance(output, dict) else None
    if (
        passed is None
        and failed is None
        and (
            parsed is None
            and (not output or (isinstance(output, str) and not output.strip()))
        )
    ):
        return None
    if parsed:
        status_text = str(parsed.get("status") or "").lower()
        if parsed.get("timeout") is True:
            return "timeout"
        if status_text in {"passed", "failed", "timeout", "error"}:
            return status_text
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
    limit: int | None = None,
    offset: int = 0,
) -> list[tuple[Submission, Task]]:
    """List submissions for simulations owned by recruiter with optional filters."""
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


def parse_test_output(test_output: str | None) -> dict[str, Any] | str | None:
    """Parse stored test_output into a dict when JSON, else return raw string."""
    if not test_output:
        return None
    try:
        parsed = json.loads(test_output)
        if isinstance(parsed, dict):
            return parsed
    except ValueError:
        return test_output
    return test_output
