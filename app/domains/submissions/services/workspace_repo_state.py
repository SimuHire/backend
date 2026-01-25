from __future__ import annotations

import contextlib

from app.domains.github_native.client import GithubClient, GithubError


async def fetch_base_template_sha(
    github_client: GithubClient, repo_full_name: str, default_branch: str | None
) -> str | None:
    try:
        branch_data = await github_client.get_branch(
            repo_full_name, default_branch or "main"
        )
        return (branch_data.get("commit") or {}).get("sha")
    except GithubError:
        return None


async def add_collaborator_if_needed(
    github_client: GithubClient, repo_full_name: str, github_username: str | None
):
    if not github_username:
        return
    with contextlib.suppress(GithubError):
        await github_client.add_collaborator(repo_full_name, github_username)
