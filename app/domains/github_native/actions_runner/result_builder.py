from __future__ import annotations

from app.domains.github_native.actions_runner.artifacts import parse_artifacts
from app.domains.github_native.actions_runner.backoff import apply_backoff
from app.domains.github_native.actions_runner.models import ActionsRunResult
from app.domains.github_native.actions_runner.normalize import normalize_run
from app.domains.github_native.actions_runner.runner_types import RunnerContext
from app.domains.github_native.actions_runner.runs import run_cache_key


async def build_result(
    ctx: RunnerContext, repo_full_name: str, run
) -> ActionsRunResult:
    base = normalize_run(run)
    parse_fn = getattr(ctx, "_parse_artifacts", None)
    parsed, artifact_error = await (
        parse_fn(repo_full_name, run.id)
        if parse_fn
        else parse_artifacts(ctx.client, ctx.cache, repo_full_name, run.id)
    )
    if parsed:
        base.passed = parsed.passed
        base.failed = parsed.failed
        base.total = parsed.total
        base.stdout = parsed.stdout
        base.stderr = parsed.stderr
        base.raw = base.raw or {}
        base.raw["summary"] = parsed.summary
    elif artifact_error and run.conclusion:
        base.status = "error"
        base.raw = base.raw or {}
        base.raw.setdefault("artifact_error", artifact_error)
        base.stderr = (
            base.stderr
            or "Test results artifact missing or unreadable. Please re-run tests."
        )
    cache_key = run_cache_key(repo_full_name, run.id)
    apply_backoff(ctx.cache, cache_key, base, ctx.poll_interval_seconds)
    return base
