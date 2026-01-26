from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime

from app.integrations.github import GithubClient, GithubError
from app.integrations.github.template_health.classify import _classify_github_error
from app.integrations.github.template_health.runs import _is_dispatched_run


async def dispatch_and_poll(
    github_client: GithubClient,
    *,
    repo_full_name: str,
    workflow_file: str,
    default_branch: str,
    timeout_seconds: int,
) -> tuple[list[str], int | None, str | None]:
    errors: list[str] = []
    dispatch_started_at = datetime.now(UTC)
    try:
        await github_client.trigger_workflow_dispatch(
            repo_full_name, workflow_file, ref=default_branch
        )
    except GithubError as exc:
        errors.append(_classify_github_error(exc) or "workflow_dispatch_failed")
        return errors, None, None

    deadline = time.monotonic() + timeout_seconds
    poll_interval = 2.0
    while time.monotonic() < deadline:
        try:
            runs = await github_client.list_workflow_runs(
                repo_full_name, workflow_file, branch=default_branch, per_page=5
            )
        except GithubError as exc:
            errors.append(_classify_github_error(exc) or "workflow_dispatch_failed")
            return errors, None, None

        run = next(
            (item for item in runs if _is_dispatched_run(item, dispatch_started_at)),
            None,
        )
        if run:
            status = (run.status or "").lower()
            conclusion = (run.conclusion or "").lower() if run.conclusion else None
            if status == "completed" or conclusion:
                return errors, int(run.id), conclusion

        await asyncio.sleep(poll_interval)
        poll_interval = min(poll_interval * 1.5, 8.0)

    return ["workflow_run_timeout"], None, None
