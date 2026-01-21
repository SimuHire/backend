from __future__ import annotations

from app.domains.github_native import GithubClient, GithubError
from app.domains.github_native.template_health.classify import _classify_github_error
from app.domains.github_native.template_health.schemas import TemplateHealthChecks


async def fetch_repo_and_branch(
    github_client: GithubClient,
    repo_full_name: str,
    checks: TemplateHealthChecks,
    errors: list[str],
) -> str | None:
    try:
        repo = await github_client.get_repo(repo_full_name)
        checks.repoReachable = True
    except GithubError as exc:
        errors.append(_classify_github_error(exc) or ("repo_not_found" if exc.status_code == 404 else "repo_unreachable"))
        return None

    default_branch = (repo.get("default_branch") or "").strip() or None
    checks.defaultBranch = default_branch
    if not default_branch:
        errors.append("default_branch_missing")
        return None

    try:
        await github_client.get_branch(repo_full_name, default_branch)
        checks.defaultBranchUsable = True
    except GithubError as exc:
        errors.append(_classify_github_error(exc) or "default_branch_unusable")
        return None
    return default_branch
