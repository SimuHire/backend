from __future__ import annotations

from fastapi import status

from app.domains.github_native.client import GithubError
from app.infra.errors import ApiError


def map_github_error(exc: GithubError) -> ApiError:
    """Return a safe ApiError for GitHub API failures."""
    code = exc.status_code or 0
    detail = "GitHub unavailable. Please try again."
    error_code = "GITHUB_UNAVAILABLE"
    retryable = False
    if code == 401:
        detail = "GitHub token is invalid or misconfigured."
        error_code = "GITHUB_TOKEN_INVALID"
    elif code == 403:
        detail = "GitHub token missing required permissions."
        error_code = "GITHUB_PERMISSION_DENIED"
    elif code == 404:
        detail = "GitHub repository or workflow not found."
        error_code = "GITHUB_NOT_FOUND"
    elif code == 429:
        detail = "GitHub rate limit exceeded. Please retry later."
        error_code = "GITHUB_RATE_LIMITED"
        retryable = True
    return ApiError(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail=detail,
        error_code=error_code,
        retryable=retryable,
    )


__all__ = ["map_github_error"]
