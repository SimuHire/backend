from __future__ import annotations

from app.domains.github_native.client import GithubError


def _classify_github_error(exc: GithubError) -> str | None:
    if exc.status_code == 403:
        return "github_forbidden"
    if exc.status_code == 429:
        return "github_rate_limited"
    return None
