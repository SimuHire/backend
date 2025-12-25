import logging
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Path, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.db import get_session
from app.domain import CandidateSession, Task
from app.domain.candidate_sessions import service as cs_service
from app.domain.submissions import service_candidate as submission_service
from app.domain.submissions.schemas import (
    ProgressSummary,
    RunTestsRequest,
    RunTestsResponse,
    SubmissionCreateRequest,
    SubmissionCreateResponse,
)
from app.services.sandbox_client import SandboxClient, SandboxError

router = APIRouter()

logger = logging.getLogger(__name__)


async def _load_candidate_session_or_404(
    db: AsyncSession,
    candidate_session_id: int,
    token: str,
) -> CandidateSession:
    return await cs_service.fetch_by_id_and_token(
        db, candidate_session_id, token, now=datetime.now(UTC)
    )


async def _compute_current_task(db: AsyncSession, cs: CandidateSession) -> Task | None:
    tasks, completed_task_ids, current, *_ = await cs_service.progress_snapshot(db, cs)
    return current


def get_sandbox_client() -> SandboxClient:
    """Default sandbox client dependency."""
    return SandboxClient(
        base_url=settings.sandbox.SANDBOX_API_URL,
        api_key=settings.sandbox.SANDBOX_API_KEY,
        default_timeout=float(settings.sandbox.SANDBOX_TIMEOUT_SECONDS),
        poll_interval_seconds=float(settings.sandbox.SANDBOX_POLL_INTERVAL_SECONDS),
        max_poll_seconds=float(settings.sandbox.SANDBOX_MAX_POLL_SECONDS),
    )


@router.post(
    "/{task_id}/submit",
    response_model=SubmissionCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def submit_task(
    task_id: Annotated[int, Path(..., ge=1)],
    payload: SubmissionCreateRequest,
    x_candidate_token: Annotated[str, Header(..., alias="x-candidate-token")],
    x_candidate_session_id: Annotated[int, Header(..., alias="x-candidate-session-id")],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> SubmissionCreateResponse:
    """Submit a task for a candidate session. Enforces ordering and idempotency."""
    cs = await _load_candidate_session_or_404(
        db, x_candidate_session_id, x_candidate_token
    )

    task = await submission_service.load_task_or_404(db, task_id)
    submission_service.ensure_task_belongs(task, cs)
    await submission_service.ensure_not_duplicate(db, cs.id, task_id)

    current_task = await _compute_current_task(db, cs)
    submission_service.ensure_in_order(current_task, task_id)
    submission_service.validate_payload(task, payload)

    now = datetime.now(UTC)
    sub = await submission_service.create_submission(db, cs, task, payload, now=now)

    completed, total, is_complete = await submission_service.progress_after_submission(
        db, cs, now=now
    )

    return SubmissionCreateResponse(
        submissionId=sub.id,
        taskId=task.id,
        candidateSessionId=cs.id,
        submittedAt=sub.submitted_at,
        progress=ProgressSummary(completed=completed, total=total),
        isComplete=is_complete,
    )


@router.post(
    "/{task_id}/run",
    response_model=RunTestsResponse,
    status_code=status.HTTP_200_OK,
)
async def run_task_tests(
    task_id: Annotated[int, Path(..., ge=1)],
    payload: RunTestsRequest,
    db: Annotated[AsyncSession, Depends(get_session)],
    sandbox_client: Annotated[SandboxClient, Depends(get_sandbox_client)],
    x_candidate_token: Annotated[str | None, Header(alias="x-candidate-token")] = None,
    x_candidate_session_id: Annotated[
        int | None, Header(alias="x-candidate-session-id")
    ] = None,
) -> RunTestsResponse:
    """Run sandbox tests for a code/debug task without persisting a submission."""
    if not x_candidate_token or x_candidate_session_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing candidate session headers",
        )

    cs = await _load_candidate_session_or_404(
        db, x_candidate_session_id, x_candidate_token
    )
    task = await submission_service.load_task_or_404(db, task_id)
    submission_service.ensure_task_belongs(task, cs)

    current_task = await _compute_current_task(db, cs)
    submission_service.ensure_in_order(current_task, task_id)
    submission_service.validate_run_payload(task, payload)

    try:
        task_ref = await submission_service.build_task_ref(db, task)
        result = await sandbox_client.run_tests(
            task_ref=task_ref,
            code=payload.codeBlob,
            files=payload.files,
        )
    except SandboxError as exc:
        logger.error(
            "sandbox_run_failed",
            extra={
                "task_id": task.id,
                "candidate_session_id": cs.id,
                "simulation_id": task.simulation_id,
                "error": str(exc),
            },
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Sandbox unavailable. Please try again.",
        ) from exc
    except Exception as exc:  # pragma: no cover - safety net
        logger.exception(
            "sandbox_run_unhandled",
            extra={
                "task_id": task.id,
                "candidate_session_id": cs.id,
                "simulation_id": task.simulation_id,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Sandbox unavailable. Please try again.",
        ) from exc

    return RunTestsResponse(
        status=result.status,
        passed=result.passed,
        failed=result.failed,
        total=result.total,
        stdout=result.stdout or None,
        stderr=result.stderr or None,
        timeout=result.timeout,
    )
