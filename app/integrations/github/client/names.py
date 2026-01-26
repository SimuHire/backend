from __future__ import annotations

from .errors import GithubError


def split_full_name(full_name: str) -> tuple[str, str]:
    if not full_name or "/" not in full_name:
        raise GithubError("Invalid repository name")
    owner, repo = full_name.split("/", 1)
    if not owner or not repo:
        raise GithubError("Invalid repository name")
    return owner, repo
