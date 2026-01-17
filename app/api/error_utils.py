from __future__ import annotations

from fastapi import HTTPException, status

from app.domains.github_native.client import GithubError


def map_github_error(exc: GithubError) -> HTTPException:
    """Return a safe HTTPException for GitHub API failures."""
    code = exc.status_code or 0
    detail = "GitHub unavailable. Please try again."
    if code in {401, 403}:
        detail = "GitHub credentials are invalid or missing permissions."
    elif code == 404:
        detail = "GitHub repository or workflow not found."
    return HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=detail)
