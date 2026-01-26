from __future__ import annotations

import re

from fastapi import status

from app.core.errors import ApiError

_BRANCH_RE = re.compile(r"^[A-Za-z0-9._/-]{1,200}$")


def validate_branch(branch: str | None) -> str | None:
    """Ensure branch names are safe-ish."""
    if branch is None:
        return None
    if not isinstance(branch, str):
        raise ApiError(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid branch name",
            error_code="INVALID_BRANCH_NAME",
        )
    if (
        ".." in branch
        or "//" in branch
        or branch.startswith("/")
        or branch.endswith("/")
    ):
        raise ApiError(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid branch name",
            error_code="INVALID_BRANCH_NAME",
        )
    if not _BRANCH_RE.match(branch):
        raise ApiError(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid branch name",
            error_code="INVALID_BRANCH_NAME",
        )
    return branch
