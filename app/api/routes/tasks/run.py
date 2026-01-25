from typing import Annotated

from fastapi import APIRouter, Depends, Path, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.candidate_sessions import candidate_session_from_headers
from app.api.dependencies.github_native import get_actions_runner
from app.api.routes.tasks.handlers import handle_run_tests
from app.domains import CandidateSession
from app.domains.github_native.actions_runner import GithubActionsRunner
from app.domains.submissions.schemas import RunTestsRequest, RunTestsResponse
from app.infra.db import get_session

router = APIRouter()


@router.post(
    "/{task_id}/run", response_model=RunTestsResponse, status_code=status.HTTP_200_OK
)
async def run_task_tests_route(
    task_id: Annotated[int, Path(..., ge=1)],
    payload: RunTestsRequest,
    db: Annotated[AsyncSession, Depends(get_session)],
    actions_runner: Annotated[GithubActionsRunner, Depends(get_actions_runner)],
    candidate_session: Annotated[
        CandidateSession, Depends(candidate_session_from_headers)
    ],
) -> RunTestsResponse:
    """Dispatch GitHub Actions tests for a candidate task."""
    return await handle_run_tests(
        task_id=task_id,
        payload=payload,
        db=db,
        actions_runner=actions_runner,
        candidate_session=candidate_session,
    )
