from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.error_utils import map_github_error
from app.api.routes.tasks.responses import build_run_response
from app.domains import CandidateSession
from app.domains.github_native.actions_runner import GithubActionsRunner
from app.domains.github_native.client import GithubError
from app.domains.submissions import service_candidate as submission_service
from app.domains.submissions.schemas import RunTestsRequest, RunTestsResponse
from app.domains.submissions.use_cases.run_tests import run_task_tests
from app.infra.errors import ApiError


async def handle_run_tests(
    task_id: int,
    payload: RunTestsRequest,
    db: AsyncSession,
    actions_runner: GithubActionsRunner,
    candidate_session: CandidateSession,
) -> RunTestsResponse:
    try:
        _, workspace, result = await run_task_tests(
            db,
            candidate_session=candidate_session,
            task_id=task_id,
            runner=actions_runner,
            branch=payload.branch,
            workflow_inputs=payload.workflowInputs,
        )
    except GithubError as exc:
        raise map_github_error(exc) from exc
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover - safety net
        raise ApiError(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="GitHub unavailable. Please try again.",
            error_code="GITHUB_UNAVAILABLE",
            retryable=True,
        ) from exc

    await submission_service.record_run_result(db, workspace, result)
    return build_run_response(result)
