from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.workspaces.workspace import Workspace


async def get_by_session_and_task(
    db: AsyncSession, *, candidate_session_id: int, task_id: int
) -> Workspace | None:
    """Fetch an existing workspace for a candidate session + task."""
    stmt = select(Workspace).where(
        Workspace.candidate_session_id == candidate_session_id,
        Workspace.task_id == task_id,
    )
    res = await db.execute(stmt)
    return res.scalar_one_or_none()


async def create_workspace(
    db: AsyncSession,
    *,
    candidate_session_id: int,
    task_id: int,
    template_repo_full_name: str,
    repo_full_name: str,
    repo_id: int | None,
    default_branch: str | None,
    base_template_sha: str | None,
    created_at,
) -> Workspace:
    """Persist a workspace record."""
    ws = Workspace(
        candidate_session_id=candidate_session_id,
        task_id=task_id,
        template_repo_full_name=template_repo_full_name,
        repo_full_name=repo_full_name,
        repo_id=repo_id,
        default_branch=default_branch,
        base_template_sha=base_template_sha,
        created_at=created_at,
    )
    db.add(ws)
    await db.commit()
    await db.refresh(ws)
    return ws
