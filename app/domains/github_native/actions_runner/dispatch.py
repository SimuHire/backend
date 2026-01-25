from __future__ import annotations

import logging
from typing import Any

from app.domains.github_native.client import GithubClient, GithubError

logger = logging.getLogger(__name__)


async def dispatch_with_fallbacks(
    client: GithubClient,
    workflow_fallbacks: list[str],
    *,
    repo_full_name: str,
    ref: str,
    inputs: dict[str, Any] | None,
    preferred_workflow: str,
) -> str:
    errors: list[tuple[str, GithubError]] = []
    tried: list[str] = []
    for wf in workflow_fallbacks:
        if wf in tried:
            continue
        tried.append(wf)
        try:
            await client.trigger_workflow_dispatch(
                repo_full_name, wf, ref=ref, inputs=inputs
            )
            if wf != preferred_workflow:
                logger.warning(
                    "github_workflow_dispatch_fallback",
                    extra={
                        "repo": repo_full_name,
                        "preferred_workflow": preferred_workflow,
                        "fallback_used": wf,
                    },
                )
            return wf
        except GithubError as exc:
            errors.append((wf, exc))
            if exc.status_code and exc.status_code != 404:
                raise
            continue
    if errors:
        raise errors[-1][1]
    raise GithubError("Workflow dispatch failed")
