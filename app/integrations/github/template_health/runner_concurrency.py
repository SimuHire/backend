from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable


async def run_with_concurrency(
    template_keys: list[str], *, concurrency: int, worker: Callable[[str], Awaitable]
):
    semaphore = asyncio.Semaphore(concurrency or 1)
    results: list = [None] * len(template_keys)

    async def _run_one(index: int, key: str):
        async with semaphore:
            results[index] = await worker(key)

    await asyncio.gather(
        *[_run_one(index, key) for index, key in enumerate(template_keys)]
    )
    return results
