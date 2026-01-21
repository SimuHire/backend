from __future__ import annotations

import asyncio
from typing import Awaitable, Callable

from app.domains.github_native import GithubClient
from app.domains.github_native.template_health.repo_check import check_template_repo
from app.domains.github_native.template_health.schemas import RunMode, TemplateHealthResponse
from app.domains.tasks.template_catalog import TEMPLATE_CATALOG


async def check_template_health(
    github_client: GithubClient,
    *,
    workflow_file: str,
    mode: RunMode = "static",
    template_keys: list[str] | None = None,
    timeout_seconds: int = 180,
    concurrency: int = 1,
) -> TemplateHealthResponse:
    selected = template_keys or list(TEMPLATE_CATALOG.keys())
    items = await _run_with_concurrency(
        selected,
        concurrency=concurrency,
        worker=lambda key: check_template_repo(
            github_client,
            template_key=key,
            repo_full_name=TEMPLATE_CATALOG[key]["repo_full_name"],
            workflow_file=workflow_file,
            mode=mode,
            timeout_seconds=timeout_seconds,
        ),
    )
    return TemplateHealthResponse(ok=all(item.ok for item in items), templates=items, mode=mode)


async def _run_with_concurrency(
    template_keys: list[str], *, concurrency: int, worker: Callable[[str], Awaitable]
):
    semaphore = asyncio.Semaphore(concurrency or 1)
    results: list = [None] * len(template_keys)

    async def _run_one(index: int, key: str):
        async with semaphore:
            results[index] = await worker(key)

    await asyncio.gather(*[_run_one(index, key) for index, key in enumerate(template_keys)])
    return results
