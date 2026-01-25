from __future__ import annotations

from app.domains.github_native.actions_runner.models import ActionsRunResult
from app.domains.github_native.actions_runner.result_builder import build_result
from app.domains.github_native.actions_runner.runner_types import RunnerContext
from app.domains.github_native.actions_runner.runs import run_cache_key


async def fetch_run_result(
    ctx: RunnerContext, *, repo_full_name: str, run_id: int
) -> ActionsRunResult:
    cache_key = run_cache_key(repo_full_name, run_id)
    cached = ctx.cache.run_cache.get(cache_key)
    if cached and ctx.cache.is_terminal(cached):
        return cached
    run = await ctx.client.get_workflow_run(repo_full_name, run_id)
    result = await build_result(ctx, repo_full_name, run)
    ctx.cache.cache_run(cache_key, result)
    return result
