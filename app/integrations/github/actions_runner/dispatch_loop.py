from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

from app.integrations.github.actions_runner.backoff import apply_backoff
from app.integrations.github.actions_runner.normalize import normalize_run
from app.integrations.github.actions_runner.result_builder import build_result
from app.integrations.github.actions_runner.runner_types import RunnerContext
from app.integrations.github.actions_runner.runs import is_dispatched_run, run_cache_key
from app.integrations.github.client import GithubError


async def dispatch_and_wait(
    ctx: RunnerContext, *, repo_full_name: str, ref: str, inputs: dict[str, Any] | None
) -> Any:
    dispatch_started_at = datetime.now(UTC)
    workflow_file = await ctx._dispatch_with_fallbacks(
        repo_full_name, ref=ref, inputs=inputs
    )
    deadline = asyncio.get_event_loop().time() + ctx.max_poll_seconds
    candidate_run = None
    while asyncio.get_event_loop().time() < deadline:
        runs = await ctx.client.list_workflow_runs(
            repo_full_name, workflow_file, branch=ref, per_page=5
        )
        candidate_run = next(
            (run for run in runs if is_dispatched_run(run, dispatch_started_at)), None
        )
        if candidate_run:
            status = (candidate_run.status or "").lower()
            conclusion = (
                (candidate_run.conclusion or "").lower()
                if candidate_run.conclusion
                else None
            )
            if conclusion or status == "completed":
                cache_key = run_cache_key(repo_full_name, candidate_run.id)
                result = await build_result(ctx, repo_full_name, candidate_run)
                ctx.cache.cache_run(cache_key, result)
                return result
        await asyncio.sleep(ctx.poll_interval_seconds)
    if candidate_run:
        cache_key = run_cache_key(repo_full_name, candidate_run.id)
        result = normalize_run(candidate_run, running=True)
        apply_backoff(ctx.cache, cache_key, result, ctx.poll_interval_seconds)
        ctx.cache.cache_run(cache_key, result)
        return result
    raise GithubError("No workflow run found after dispatch")
