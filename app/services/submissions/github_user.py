from __future__ import annotations

import re

from fastapi import status

from app.core.errors import ApiError

_GITHUB_USERNAME_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$")


def validate_github_username(username: str) -> None:
    """Ensure GitHub username follows GitHub rules."""
    if not username or len(username) > 39 or not _GITHUB_USERNAME_RE.match(username):
        raise ApiError(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid GitHub username",
            error_code="INVALID_GITHUB_USERNAME",
        )
