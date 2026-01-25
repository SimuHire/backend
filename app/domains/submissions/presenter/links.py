from __future__ import annotations


def build_links(repo_full_name: str | None, commit_sha: str | None, workflow_run_id):
    commit_url = (
        f"https://github.com/{repo_full_name}/commit/{commit_sha}"
        if repo_full_name and commit_sha
        else None
    )
    workflow_url = (
        f"https://github.com/{repo_full_name}/actions/runs/{workflow_run_id}"
        if repo_full_name and workflow_run_id
        else None
    )
    return commit_url, workflow_url


def build_diff_url(repo_full_name: str | None, diff_summary):
    if not repo_full_name or not isinstance(diff_summary, dict):
        return None
    base = diff_summary.get("base")
    head = diff_summary.get("head")
    if base and head:
        return f"https://github.com/{repo_full_name}/compare/{base}...{head}"
    return None
