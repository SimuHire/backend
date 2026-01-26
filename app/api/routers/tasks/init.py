from typing import Annotated

from fastapi import APIRouter, Depends, Path, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.candidate_sessions import candidate_session_from_headers
from app.api.dependencies.github_native import get_github_client
from app.api.routers.tasks.handlers import handle_codespace_init
from app.core.db import get_session
from app.domains import CandidateSession
from app.domains.submissions.schemas import CodespaceInitRequest, CodespaceInitResponse
from app.integrations.github import GithubClient

router = APIRouter()


@router.post(
    "/{task_id}/codespace/init",
    response_model=CodespaceInitResponse,
    status_code=status.HTTP_200_OK,
)
async def init_codespace_route(
    task_id: Annotated[int, Path(..., ge=1)],
    payload: CodespaceInitRequest,
    candidate_session: Annotated[
        CandidateSession, Depends(candidate_session_from_headers)
    ],
    db: Annotated[AsyncSession, Depends(get_session)],
    github_client: Annotated[GithubClient, Depends(get_github_client)],
) -> CodespaceInitResponse:
    """Provision or return a GitHub Codespace workspace for a task."""
    return await handle_codespace_init(
        task_id=task_id,
        payload=payload,
        candidate_session=candidate_session,
        db=db,
        github_client=github_client,
    )
