from typing import Annotated

from fastapi import APIRouter, Depends, Path, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.candidate_sessions import candidate_session_from_headers
from app.api.dependencies.github_native import get_actions_runner
from app.api.error_utils import map_github_error
from app.api.routes.tasks.responses import build_run_response
from app.domains import CandidateSession
from app.domains.github_native.actions_runner import GithubActionsRunner
from app.domains.github_native.client import GithubError
from app.domains.submissions import service_candidate as submission_service
from app.domains.submissions.schemas import RunTestsResponse
from app.domains.submissions.use_cases.fetch_run import fetch_run_result
from app.infra.db import get_session

router = APIRouter()


@router.get(
    "/{task_id}/run/{run_id}",
    response_model=RunTestsResponse,
    status_code=status.HTTP_200_OK,
)
async def get_run_result_route(
    task_id: Annotated[int, Path(..., ge=1)],
    run_id: Annotated[int, Path(..., ge=1)],
    db: Annotated[AsyncSession, Depends(get_session)],
    actions_runner: Annotated[GithubActionsRunner, Depends(get_actions_runner)],
    candidate_session: Annotated[
        CandidateSession, Depends(candidate_session_from_headers)
    ],
) -> RunTestsResponse:
    """Poll a previously-triggered workflow run."""
    try:
        task, workspace, result = await fetch_run_result(
            db,
            candidate_session=candidate_session,
            task_id=task_id,
            run_id=run_id,
            runner=actions_runner,
        )
    except GithubError as exc:
        raise map_github_error(exc) from exc

    await submission_service.record_run_result(db, workspace, result)
    return build_run_response(result)
