from __future__ import annotations

import logging

import httpx

from .errors import GithubError, raise_for_status
from .transport import GithubTransport

logger = logging.getLogger(__name__)


async def request_json(
    transport: GithubTransport,
    method: str,
    path: str,
    *,
    params: dict | None = None,
    json: dict | None = None,
    expect_body: bool = True,
) -> dict:
    try:
        resp = await transport.client().request(method, path, params=params, json=json)
    except httpx.HTTPError as exc:  # pragma: no cover - network
        logger.error(
            "github_request_failed",
            extra={"url": f"{transport.base_url}{path}", "error": str(exc)},
        )
        raise GithubError("GitHub request failed") from exc

    raise_for_status(str(resp.url), resp)
    if not expect_body:
        return {}
    if "application/zip" in resp.headers.get("Content-Type", ""):
        return resp.content  # type: ignore[return-value]
    try:
        return resp.json()
    except ValueError as exc:
        raise GithubError("Invalid GitHub response") from exc


async def get_bytes(
    transport: GithubTransport, path: str, params: dict | None = None
) -> bytes:
    try:
        resp = await transport.client().get(path, params=params, follow_redirects=True)
    except httpx.HTTPError as exc:  # pragma: no cover - network
        logger.error(
            "github_request_failed",
            extra={"url": f"{transport.base_url}{path}", "error": str(exc)},
        )
        raise GithubError("GitHub request failed") from exc

    raise_for_status(str(resp.url), resp)
    return resp.content
