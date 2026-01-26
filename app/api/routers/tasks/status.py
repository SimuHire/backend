from typing import Annotated

from fastapi import APIRouter, Depends, Path, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.candidate_sessions import candidate_session_from_headers
from app.core.db import get_session
from app.domains import CandidateSession
from app.domains.submissions.schemas import CodespaceStatusResponse
from app.domains.submissions.use_cases.codespace_status import codespace_status

router = APIRouter()


@router.get(
    "/{task_id}/codespace/status",
    response_model=CodespaceStatusResponse,
    status_code=status.HTTP_200_OK,
)
async def codespace_status_route(
    task_id: Annotated[int, Path(..., ge=1)],
    candidate_session: Annotated[
        CandidateSession, Depends(candidate_session_from_headers)
    ],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> CodespaceStatusResponse:
    """Return Codespace details and last known test status for a task."""
    workspace, last_test_summary, codespace_url, _ = await codespace_status(
        db, candidate_session=candidate_session, task_id=task_id
    )
    return CodespaceStatusResponse(
        repoFullName=workspace.repo_full_name,
        repoUrl=f"https://github.com/{workspace.repo_full_name}",
        codespaceUrl=codespace_url,
        defaultBranch=workspace.default_branch,
        latestCommitSha=workspace.latest_commit_sha,
        lastWorkflowRunId=workspace.last_workflow_run_id,
        lastWorkflowConclusion=workspace.last_workflow_conclusion,
        lastTestSummary=last_test_summary,
        workspaceId=workspace.id,
    )
