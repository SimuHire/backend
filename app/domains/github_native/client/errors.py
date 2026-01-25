from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)


class GithubError(Exception):
    """Raised when GitHub API calls fail."""

    def __init__(self, message: str, *, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


def raise_for_status(url: str, resp: httpx.Response) -> None:
    if resp.status_code < 400:
        return
    logger.error(
        "github_error",
        extra={"url": url, "status_code": resp.status_code},
    )
    raise GithubError(
        f"GitHub API error ({resp.status_code}) ({url})",
        status_code=resp.status_code,
    )
