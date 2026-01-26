from typing import Annotated

from fastapi import APIRouter, Depends, Path, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.candidate_sessions import candidate_session_from_headers
from app.api.dependencies.github_native import get_actions_runner, get_github_client
from app.api.routers.tasks.handlers import handle_submit_task
from app.core.db import get_session
from app.domains import CandidateSession
from app.domains.submissions.schemas import (
    SubmissionCreateRequest,
    SubmissionCreateResponse,
)
from app.integrations.github import GithubClient
from app.integrations.github.actions_runner import GithubActionsRunner

router = APIRouter()


@router.post(
    "/{task_id}/submit",
    response_model=SubmissionCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def submit_task_route(
    task_id: Annotated[int, Path(..., ge=1)],
    payload: SubmissionCreateRequest,
    candidate_session: Annotated[
        CandidateSession, Depends(candidate_session_from_headers)
    ],
    db: Annotated[AsyncSession, Depends(get_session)],
    github_client: Annotated[GithubClient, Depends(get_github_client)],
    actions_runner: Annotated[GithubActionsRunner, Depends(get_actions_runner)],
) -> SubmissionCreateResponse:
    """Submit a task, optionally running GitHub tests for code/debug types."""
    return await handle_submit_task(
        task_id=task_id,
        payload=payload,
        candidate_session=candidate_session,
        db=db,
        github_client=github_client,
        actions_runner=actions_runner,
    )
