from __future__ import annotations

import logging

from app.core.settings import settings
from app.domains.submissions import service_candidate as submission_service
from app.integrations.github import GithubClient, GithubError

logger = logging.getLogger(__name__)


async def preprovision_workspaces(
    db,
    candidate_session,
    tasks,
    github_client: GithubClient,
    *,
    now,
) -> None:
    repo_prefix = settings.github.GITHUB_REPO_PREFIX
    template_owner = settings.github.GITHUB_TEMPLATE_OWNER or settings.github.GITHUB_ORG
    for task in tasks:
        task_type = str(task.type or "").lower()
        if task.day_index not in {2, 3} or task_type not in {"code", "debug"}:
            continue
        try:
            await submission_service.ensure_workspace(
                db,
                candidate_session=candidate_session,
                task=task,
                github_client=github_client,
                github_username="",
                repo_prefix=repo_prefix,
                template_default_owner=template_owner,
                now=now,
            )
        except GithubError as exc:
            logger.error(
                "github_workspace_preprovision_failed",
                extra={
                    "simulation_id": getattr(candidate_session, "simulation_id", None),
                    "candidate_session_id": getattr(candidate_session, "id", None),
                    "task_id": task.id,
                    "day_index": task.day_index,
                    "template_repo": (task.template_repo or "").strip(),
                    "repo_name": submission_service.build_repo_name(
                        prefix=repo_prefix,
                        candidate_session=candidate_session,
                        task=task,
                    ),
                    "status_code": getattr(exc, "status_code", None),
                },
            )
            raise
